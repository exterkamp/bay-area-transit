from datetime import timedelta

import pytest
from django.utils import timezone
from google.transit import gtfs_realtime_pb2 as rt

from transit import queries
from transit.gtfs.importer import FeedFilter, import_feed
from transit.models import Alert, RealtimeFetch, TripUpdate, VehiclePosition
from transit.realtime.poller import store

from .conftest import REGIONAL, local

WEDNESDAY = (2026, 10, 28)


def message(build):
    msg = rt.FeedMessage()
    msg.header.gtfs_realtime_version = "2.0"
    msg.header.timestamp = 1792873150
    build(msg)
    return msg


def trip_update(msg, trip_id, *stops, canceled=False, delay=None):
    entity = msg.entity.add(id=trip_id)
    tu = entity.trip_update
    tu.trip.trip_id = trip_id
    if canceled:
        tu.trip.schedule_relationship = rt.TripDescriptor.CANCELED
    if delay is not None:
        tu.delay = delay
    for stop_id, arrival, departure, *rest in stops:
        stu = tu.stop_time_update.add(stop_id=stop_id)
        if arrival:
            stu.arrival.time = int(arrival.timestamp())
        if departure:
            stu.departure.time = int(departure.timestamp())
        if rest and rest[0] == "skipped":
            stu.schedule_relationship = rt.TripUpdate.StopTimeUpdate.SKIPPED


@pytest.fixture
def ctx(feed):
    return queries.context_for("TT")


def test_absolute_times_become_delays_and_propagate(ctx):
    # 511 style: absolute times by stop_id, no start_date, no stop_sequence.
    store(
        ctx.operator,
        "trip_updates",
        message(
            lambda m: trip_update(
                m, "T1", ("mid_nb", local(*WEDNESDAY, 8, 13), local(*WEDNESDAY, 8, 14))
            )
        ),
    )
    result = queries.plan(ctx, "mid", "north", local(*WEDNESDAY, 8))
    trip = result["trips"][0]
    assert trip["status"] == "live"
    assert trip["depart"]["delay_seconds"] == 180
    assert trip["depart"]["estimated"] == "2026-10-28T08:14:00-07:00"
    # No update for north: mid's delay carries forward.
    assert trip["arrive"]["delay_seconds"] == 180
    assert trip["arrive"]["estimated"] == "2026-10-28T08:23:00-07:00"


def test_stops_before_first_update_have_no_estimate(ctx):
    store(
        ctx.operator,
        "trip_updates",
        message(lambda m: trip_update(m, "T1", ("north_nb", local(*WEDNESDAY, 8, 25), None))),
    )
    trip = queries.trip_detail(ctx, "T1", local(*WEDNESDAY).date())
    assert trip["stops"][0]["departure"]["estimated"] is None
    assert trip["stops"][2]["arrival"]["delay_seconds"] == 300


def test_late_train_still_listed_after_its_scheduled_time(ctx):
    store(
        ctx.operator,
        "trip_updates",
        message(lambda m: trip_update(m, "T1", ("south_nb", None, local(*WEDNESDAY, 8, 12)))),
    )
    result = queries.plan(ctx, "south", "north", local(*WEDNESDAY, 8, 5))
    assert result["trips"][0]["trip_id"] == "T1"


def test_canceled_trip(ctx):
    store(ctx.operator, "trip_updates", message(lambda m: trip_update(m, "T2", canceled=True)))
    result = queries.plan(ctx, "south", "north", local(*WEDNESDAY, 8, 25))
    assert result["trips"][0]["trip_id"] == "T2"
    assert result["trips"][0]["status"] == "canceled"


def test_skipped_stop_cancels_that_ride(ctx):
    store(
        ctx.operator,
        "trip_updates",
        message(lambda m: trip_update(m, "T1", ("mid_nb", None, None, "skipped"))),
    )
    result = queries.plan(ctx, "mid", "north", local(*WEDNESDAY, 8))
    assert result["trips"][0]["status"] == "canceled"


def test_trip_level_delay(ctx):
    store(ctx.operator, "trip_updates", message(lambda m: trip_update(m, "T1", delay=120)))
    trip = queries.plan(ctx, "south", "north", local(*WEDNESDAY, 7))["trips"][0]
    assert trip["depart"]["delay_seconds"] == 120


def test_prediction_for_another_day_is_ignored(ctx):
    # Same trip_id, but the prediction is a day off: it's tomorrow's train.
    store(
        ctx.operator,
        "trip_updates",
        message(lambda m: trip_update(m, "T1", ("mid_nb", None, local(2026, 10, 29, 8, 11)))),
    )
    trip = queries.plan(ctx, "mid", "north", local(*WEDNESDAY, 8))["trips"][0]
    assert trip["status"] == "scheduled"


def test_stale_realtime_is_ignored(ctx):
    store(ctx.operator, "trip_updates", message(lambda m: trip_update(m, "T1", delay=120)))
    RealtimeFetch.objects.update(fetched_at=timezone.now() - timedelta(hours=1))
    trip = queries.plan(ctx, "south", "north", local(*WEDNESDAY, 7))["trips"][0]
    assert trip["status"] == "scheduled"


def test_each_poll_replaces_the_snapshot(ctx):
    store(ctx.operator, "trip_updates", message(lambda m: trip_update(m, "T1", delay=60)))
    store(ctx.operator, "trip_updates", message(lambda m: trip_update(m, "T2", delay=60)))
    assert list(TripUpdate.objects.values_list("trip_id", flat=True)) == ["T2"]
    fetch = RealtimeFetch.objects.get(kind="trip_updates")
    assert fetch.entity_count == 1
    assert fetch.feed_timestamp is not None


def test_vehicle_positions(ctx):
    def build(m):
        v = m.entity.add(id="v1").vehicle
        v.trip.trip_id = "T1"
        v.vehicle.id = "128"
        v.position.latitude = 37.5
        v.position.longitude = -122.2
        v.position.bearing = 400  # out of range: normalized
        v.current_status = rt.VehiclePosition.IN_TRANSIT_TO
        v.stop_id = "mid_nb"
        v.timestamp = 1792873147
        bad = m.entity.add(id="v2").vehicle
        bad.position.latitude = 0
        bad.position.longitude = 0  # null island: dropped

    store(ctx.operator, "vehicle_positions", message(build))
    assert VehiclePosition.objects.count() == 1
    [vehicle] = queries.vehicles(ctx)
    assert vehicle["short_name"] == "101"
    assert vehicle["route"]["id"] == "LOC"
    assert vehicle["bearing"] == 40
    assert vehicle["status"] == "in_transit_to"
    assert (
        queries.trip_detail(ctx, "T1", local(*WEDNESDAY).date())["vehicle"]["vehicle_id"] == "128"
    )


def test_alerts(ctx):
    def build(m):
        a = m.entity.add(id="a1").alert
        a.header_text.translation.add(text="Delays", language="en")
        a.description_text.translation.add(text="Retrasos", language="es")
        a.cause = rt.Alert.TECHNICAL_PROBLEM
        a.effect = rt.Alert.SIGNIFICANT_DELAYS
        a.informed_entity.add(route_id="LOC")
        a.informed_entity.add(stop_id="mid_nb")
        a.active_period.add(start=1)

    store(ctx.operator, "alerts", message(build))
    alert = Alert.objects.get()
    assert alert.header == "Delays"
    assert alert.description == "Retrasos"  # only translation available
    assert alert.cause == "technical_problem"
    assert alert.route_ids == ["LOC"]
    assert alert.active_periods == [[1, None]]


class TestFilteredFeed:
    """A regional feed imported with a filter keeps realtime only for what it kept."""

    @pytest.fixture
    def regional(self, operator):
        import_feed(operator, REGIONAL, only=FeedFilter.parse("RA:0"))
        operator.refresh_from_db()
        return operator

    def test_trip_updates_for_dropped_trips_are_dropped(self, regional):
        def build(m):
            for trip_id in ("RA:1", "RA:2", "BU:1", "ZZ:7"):
                trip_update(m, trip_id, delay=60)

        assert store(regional, "trip_updates", message(build)) == 1
        assert list(TripUpdate.objects.values_list("trip_id", flat=True)) == ["RA:1"]
        assert RealtimeFetch.objects.get(kind="trip_updates").entity_count == 1

    def test_stop_time_updates_attach_to_their_trip(self, regional):
        def build(m):
            trip_update(m, "BU:1", ("corner", None, local(*WEDNESDAY, 8)))
            trip_update(m, "RA:1", ("hub_rail", None, local(*WEDNESDAY, 8)))

        store(regional, "trip_updates", message(build))
        [update] = TripUpdate.objects.prefetch_related("stop_time_updates")
        assert [s.stop_id for s in update.stop_time_updates.all()] == ["hub_rail"]

    def test_vehicles_need_a_kept_trip(self, regional):
        def build(m):
            for vid, trip_id in (("1", "RA:1"), ("2", "BU:1"), ("3", "")):
                v = m.entity.add(id=vid).vehicle
                if trip_id:
                    v.trip.trip_id = trip_id
                v.position.latitude = 37.5
                v.position.longitude = -122.2

        assert store(regional, "vehicle_positions", message(build)) == 1
        assert VehiclePosition.objects.get().trip_id == "RA:1"

    def test_alerts_must_inform_something_kept(self, regional):
        def build(m):
            m.entity.add(id="agency").alert.informed_entity.add(agency_id="RA")
            m.entity.add(id="route").alert.informed_entity.add(route_id="RA:L")
            m.entity.add(id="stop").alert.informed_entity.add(stop_id="far_rail")
            m.entity.add(id="other-agency").alert.informed_entity.add(agency_id="BU")
            m.entity.add(id="cable-car").alert.informed_entity.add(agency_id="RA", route_id="RA:CC")
            mixed = m.entity.add(id="mixed").alert
            mixed.informed_entity.add(route_id="BU:1")
            mixed.informed_entity.add(route_id="RA:L")

        store(regional, "alerts", message(build))
        assert set(Alert.objects.values_list("alert_id", flat=True)) == {
            "agency",
            "route",
            "stop",
            "mixed",
        }

    def test_unfiltered_feed_keeps_unknown_trips(self, ctx):
        # Added trips aren't in the static feed; without a filter, keep them.
        store(ctx.operator, "trip_updates", message(lambda m: trip_update(m, "EXTRA", delay=0)))
        assert TripUpdate.objects.get().trip_id == "EXTRA"
