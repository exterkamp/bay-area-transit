from datetime import date

import pytest

from transit import queries
from transit.queries import BadRequest, NotFound

from .conftest import local

WEDNESDAY = (2026, 10, 28)


@pytest.fixture
def ctx(feed):
    return queries.context_for("TT")


def same_day(result, day="2026-10-28"):
    return [t["trip_id"] for t in result["trips"] if t["service_date"] == day]


def times(trip):
    return trip["depart"]["scheduled"][11:16], trip["arrive"]["scheduled"][11:16]


def test_next_trains_in_order(ctx):
    result = queries.plan(ctx, "south", "north", local(*WEDNESDAY, 7, 55))
    assert same_day(result) == ["T1", "T2", "T6"]
    first = result["trips"][0]
    assert times(first) == ("08:00", "08:20")
    assert first["depart"]["scheduled"] == "2026-10-28T08:00:00-07:00"
    assert first["depart"]["platform"] == "South Northbound"
    assert first["duration_minutes"] == 20
    assert first["stops_between"] == 1
    assert first["status"] == "scheduled"
    assert first["route"] == {
        "id": "LOC",
        "short_name": "Local",
        "color": "#99d7dc",
        "text_color": "#000000",
        "agency": "TT",
        "type": 2,
    }
    express = result["trips"][1]
    assert express["stops_between"] == 0
    assert express["route"]["text_color"] == "#000000"  # blank in feed -> default


def test_fare_is_zone_based(ctx):
    assert queries.plan(ctx, "south", "north", local(*WEDNESDAY, 7))["fare"] == {
        "price": "3.75",
        "currency": "USD",
    }
    assert queries.plan(ctx, "south", "mid", local(*WEDNESDAY, 7))["fare"]["price"] == "2.50"


def test_direction_matters(ctx):
    # Northbound-only trips can't take you south.
    result = queries.plan(ctx, "north", "south", local(*WEDNESDAY, 7))
    assert same_day(result) == ["T3"]


def test_express_skips_mid(ctx):
    # T2 runs straight through; T6 sets down at mid (it just won't pick up there).
    result = queries.plan(ctx, "south", "mid", local(*WEDNESDAY, 7, 55))
    assert same_day(result) == ["T1", "T6"]


def test_no_pickup_stop_is_not_a_boarding(ctx):
    result = queries.plan(ctx, "mid", "north", local(*WEDNESDAY, 8, 30))
    assert same_day(result) == []  # T6 doesn't pick up at mid
    assert result["trips"][0]["service_date"] == "2026-10-29"


def test_limit(ctx):
    assert len(queries.plan(ctx, "south", "north", local(*WEDNESDAY, 7), limit=1)["trips"]) == 1
    with pytest.raises(BadRequest):
        queries.plan(ctx, "south", "north", local(*WEDNESDAY, 7), limit=0)


def test_rolls_over_to_next_service_day(ctx):
    # After the last northbound train on Wednesday, Thursday's come up.
    result = queries.plan(ctx, "south", "north", local(*WEDNESDAY, 22))
    assert result["trips"][0]["service_date"] == "2026-10-29"


def test_after_midnight_trip_belongs_to_previous_service_day(ctx):
    result = queries.plan(ctx, "mid", "south", local(2026, 10, 29, 0, 5))
    trip = result["trips"][0]
    assert trip["trip_id"] == "T3"
    assert trip["service_date"] == "2026-10-28"
    assert trip["depart"]["scheduled"] == "2026-10-29T00:10:00-07:00"


def test_thanksgiving_runs_weekend_service(ctx):
    result = queries.plan(ctx, "south", "north", local(2026, 11, 26, 7))
    assert result["trips"][0]["trip_id"] == "T4"


def test_untimed_stop_uses_interpolated_time(ctx):
    result = queries.plan(ctx, "mid", "north", local(2026, 10, 24, 9))
    assert times(result["trips"][0]) == ("10:05", "10:20")


def test_bad_requests(ctx):
    at = local(*WEDNESDAY, 7)
    with pytest.raises(BadRequest):
        queries.plan(ctx, "south", "south", at)
    with pytest.raises(BadRequest):
        queries.plan(ctx, "", "south", at)
    with pytest.raises(NotFound):
        queries.plan(ctx, "south", "atlantis", at)
    with pytest.raises(BadRequest):
        # A platform resolves to its station, so this is south to south.
        queries.plan(ctx, "south_nb", "south", at)


def test_a_platform_id_resolves_to_its_station(ctx):
    result = queries.plan(ctx, "south_nb", "north", local(*WEDNESDAY, 7, 55))
    assert result["from"] == {"id": "south", "name": "South"}
    assert result["trips"]


def test_departure_board(ctx):
    board = queries.departures(ctx, "mid", local(*WEDNESDAY, 8))
    assert [(d["trip_id"], d["destination"]["id"]) for d in board["departures"]][:2] == [
        ("T1", "north"),
        ("T3", "south"),
    ]


def test_last_stop_is_not_a_departure(ctx):
    board = queries.departures(ctx, "north", local(*WEDNESDAY, 7))
    assert {d["trip_id"] for d in board["departures"]} == {"T3"}


def test_trip_detail(ctx):
    trip = queries.trip_detail(ctx, "T1", date(*WEDNESDAY))
    assert [s["station_id"] for s in trip["stops"]] == ["south", "mid", "north"]
    assert trip["stops"][1]["arrival"]["scheduled"][11:16] == "08:10"
    assert trip["stops"][1]["departure"]["scheduled"][11:16] == "08:11"
    assert trip["bikes_allowed"] is True
    assert trip["vehicle"] is None


def test_trip_not_running_that_day(ctx):
    with pytest.raises(NotFound):
        queries.trip_detail(ctx, "T1", date(2026, 10, 24))


def test_stations_run_north_to_south(ctx):
    stations = queries.stations(ctx)
    assert [s["id"] for s in stations] == ["north", "mid", "south"]
    north = stations[0]
    assert north["wheelchair_boarding"] == "accessible"
    assert [p["id"] for p in north["platforms"]] == ["north_nb", "north_sb"]
    # Entrances aren't platforms.
    assert [p["id"] for p in stations[1]["platforms"]] == ["mid_nb", "mid_sb"]


def test_no_active_feed(operator):
    with pytest.raises(NotFound, match="no active feed"):
        queries.context_for("TT")


def test_empty_plan_says_whether_the_trip_runs_on_other_days(ctx):
    # North to mid is T3, weekdays only. Early Saturday, the window (Saturday
    # and Sunday) has nothing, but the trip exists.
    result = queries.plan(ctx, "north", "mid", local(2026, 10, 31, 1))
    assert result["trips"] == []
    assert result["served"] is True


def test_served_is_only_reported_for_empty_plans(ctx):
    assert "served" not in queries.plan(ctx, "south", "north", local(*WEDNESDAY, 7))
