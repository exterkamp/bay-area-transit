from datetime import timedelta

import pytest
from django.contrib.gis.geos import LineString, Point
from django.utils import timezone

from transit import queries
from transit.models import RealtimeFetch, VehicleStatus
from transit.realtime.estimate import TimedStop, place
from transit.realtime.poller import store

from .conftest import local
from .test_realtime import WEDNESDAY, message, trip_update

SOUTH, MID, NORTH = Point(-122.1, 37.4), Point(-122.1, 37.6), Point(-122.1, 37.8)


def at(h, m, s=0):
    return local(*WEDNESDAY, h, m, s)


STOPS = [
    TimedStop(1, "south", SOUTH, at(8, 0), at(8, 0)),
    TimedStop(2, "mid", MID, at(8, 10), at(8, 11)),
    TimedStop(3, "north", NORTH, at(8, 20), at(8, 20)),
]


class TestPlace:
    def test_not_running(self):
        assert place(STOPS, at(7, 59)) is None
        assert place(STOPS, at(8, 21)) is None

    def test_standing_at_a_platform(self):
        where = place(STOPS, at(8, 10, 30))
        assert (where.stop_id, where.status) == ("mid", VehicleStatus.STOPPED_AT)
        assert where.point == MID

    def test_between_stops_in_proportion_to_time(self):
        where = place(STOPS, at(8, 15, 30))
        assert (where.stop_id, where.status) == ("north", VehicleStatus.IN_TRANSIT_TO)
        assert where.point.y == pytest.approx(37.7)
        assert where.bearing == 0  # due north

    def test_follows_the_shape(self):
        # A dog-leg: east, then north. Halfway in time is the corner.
        bend = LineString((-122.1, 37.4), (-121.9, 37.4), (-121.9, 37.6), srid=4326)
        stops = [
            TimedStop(1, "a", Point(-122.1, 37.4), at(9, 0), at(9, 0)),
            TimedStop(2, "b", Point(-121.9, 37.6), at(9, 10), at(9, 10)),
        ]
        where = place(stops, at(9, 5), bend)
        assert (where.point.x, where.point.y) == pytest.approx((-121.9, 37.4))
        assert place(stops, at(9, 2), bend).bearing == 90  # still heading east

    def test_a_shape_running_the_other_way_is_ignored(self):
        backwards = LineString((-122.1, 37.8), (-122.1, 37.4), srid=4326)
        where = place(STOPS, at(8, 15, 30), backwards)
        assert where.point.y == pytest.approx(37.7)


@pytest.fixture
def ctx(feed):
    return queries.context_for("TT")


def estimated(ctx, now):
    return [v for v in queries.vehicles(ctx, now=now) if v["source"] == "estimated"]


class TestVehicles:
    def test_a_trip_with_predictions_but_no_gps_is_estimated(self, ctx):
        # Two minutes late at mid.
        store(
            ctx.operator,
            "trip_updates",
            message(lambda m: trip_update(m, "T1", ("mid_nb", at(8, 12), at(8, 13)))),
        )
        [v] = estimated(ctx, at(8, 12, 30))
        assert v["trip_id"] == "T1"
        assert (v["status"], v["stop_id"]) == ("stopped_at", "mid_nb")
        assert v["vehicle_id"] is None
        assert v["route"]["id"] == "LOC"

    def test_stops_behind_the_first_prediction_share_its_delay(self, ctx):
        # Only north is predicted, five minutes late; mid is behind the train.
        store(
            ctx.operator,
            "trip_updates",
            message(lambda m: trip_update(m, "T1", ("north_nb", at(8, 25), None))),
        )
        # Scheduled 8:10-8:11 at mid, so 8:15-8:16 five minutes late.
        [v] = estimated(ctx, at(8, 15, 30))
        assert (v["status"], v["stop_id"]) == ("stopped_at", "mid_nb")

    def test_gps_wins(self, ctx):
        store(
            ctx.operator,
            "trip_updates",
            message(lambda m: trip_update(m, "T1", ("mid_nb", at(8, 12), at(8, 13)))),
        )

        def build(m):
            v = m.entity.add(id="v1").vehicle
            v.trip.trip_id = "T1"
            v.position.latitude = 37.5
            v.position.longitude = -122.2

        store(ctx.operator, "vehicle_positions", message(build))
        [v] = queries.vehicles(ctx, now=at(8, 12, 30))
        assert v["source"] == "gps"

    def test_stale_predictions_place_nothing(self, ctx):
        store(
            ctx.operator,
            "trip_updates",
            message(lambda m: trip_update(m, "T1", ("mid_nb", at(8, 12), at(8, 13)))),
        )
        RealtimeFetch.objects.update(fetched_at=timezone.now() - timedelta(hours=1))
        assert estimated(ctx, at(8, 12, 30)) == []

    def test_canceled_trips_are_not_placed(self, ctx):
        store(ctx.operator, "trip_updates", message(lambda m: trip_update(m, "T1", canceled=True)))
        assert estimated(ctx, at(8, 12, 30)) == []

    def test_trip_detail_shows_the_estimate(self, ctx):
        store(
            ctx.operator,
            "trip_updates",
            message(lambda m: trip_update(m, "T1", ("mid_nb", at(8, 12), at(8, 13)))),
        )
        detail = queries.trip_detail(ctx, "T1", at(8, 0).date(), now=at(8, 12, 30))
        assert detail["vehicle"]["source"] == "estimated"
        assert detail["vehicle"]["stop_id"] == "mid_nb"


def test_a_vehicle_id_shared_by_several_trips_is_dropped(ctx):
    def build(m):
        for trip_id, stop in (
            ("T1", ("mid_nb", at(8, 12), at(8, 13))),
            ("T6", ("mid_nb", at(9, 10), at(9, 10))),
        ):
            trip_update(m, trip_id, stop)
            m.entity[-1].trip_update.vehicle.id = "3-door"

    store(ctx.operator, "trip_updates", message(build))
    [v] = estimated(ctx, at(8, 12, 30))
    assert v["vehicle_id"] is None
