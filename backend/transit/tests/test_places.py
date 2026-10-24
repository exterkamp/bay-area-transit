import shutil

import pytest

from transit import queries
from transit.gtfs.importer import delete_feed, import_feed
from transit.models import Place, Stop
from transit.queries import BadRequest, NotFound

from .conftest import REGIONAL, local

WEDNESDAY = (2026, 10, 28)

# Elm & Oak: two stops across the street from each other, and one with the
# same name in another town.
EXTRA_STOPS = """\
elm_n,Elm & Oak,37.6100,-122.3000,0,
elm_s,Elm & Oak,37.6103,-122.3002,0,
elm_far,Elm & Oak,37.9000,-122.6000,0,
lonely,Lonely Corner,37.3000,-122.0000,0,
"""
EXTRA_TRIPS = """\
BU:1,BU:WK,BU:2,Corner,
BU:1,BU:WK,BU:3,Elm,
BU:1,BU:WK,BU:4,Corner,
"""
EXTRA_STOP_TIMES = """\
BU:2,09:00:00,09:00:00,elm_n,1
BU:2,09:10:00,09:10:00,corner,2
BU:3,09:30:00,09:30:00,corner,1
BU:3,09:40:00,09:40:00,elm_s,2
BU:4,09:00:00,09:00:00,elm_far,1
BU:4,09:30:00,09:30:00,corner,2
"""


@pytest.fixture
def ctx(operator, tmp_path):
    target = tmp_path / "regional"
    shutil.copytree(REGIONAL, target)
    for name, extra in (
        ("stops.txt", EXTRA_STOPS),
        ("trips.txt", EXTRA_TRIPS),
        ("stop_times.txt", EXTRA_STOP_TIMES),
    ):
        with open(target / name, "a") as f:
            f.write(extra)
    import_feed(operator, target)
    return queries.context_for(operator.code)


def place_of(ctx, stop_id):
    return Stop.objects.get(feed=ctx.feed, stop_id=stop_id).place


class TestBuilding:
    def test_a_station_is_one_place_with_its_platforms(self, ctx):
        hub = Place.objects.get(feed=ctx.feed, place_id="hub")
        assert hub.kind == "station"
        assert {s.stop_id for s in hub.stops.all()} == {"hub", "hub_rail", "hub_bay"}
        assert {r.route_id for r in hub.routes.all()} == {"RA:L", "RA:CC", "BU:1"}

    def test_same_name_across_the_street_is_one_place(self, ctx):
        assert place_of(ctx, "elm_n") == place_of(ctx, "elm_s")
        group = place_of(ctx, "elm_n")
        assert (group.place_id, group.kind) == ("elm_n", "stop")
        assert 37.6100 < group.lat < 37.6103

    def test_same_name_in_another_town_is_not(self, ctx):
        assert place_of(ctx, "elm_far") != place_of(ctx, "elm_n")

    def test_entrances_belong_to_no_place(self, operator):
        from .conftest import MINI

        feed = import_feed(operator, MINI).feed
        assert Stop.objects.get(feed=feed, stop_id="mid_entrance").place is None
        assert Stop.objects.get(feed=feed, stop_id="mid_nb").place.place_id == "mid"

    def test_deleting_a_feed_deletes_its_places(self, ctx):
        delete_feed(ctx.feed)
        assert not Place.objects.exists()
        assert not Place.routes.through.objects.exists()


class TestPlanning:
    def test_either_side_of_the_street_boards_the_right_direction(self, ctx):
        # Asked from the southbound stop's id; the trip leaves from the other side.
        result = queries.plan(ctx, "elm_s", "corner", local(*WEDNESDAY, 8, 30))
        assert result["from"] == {"id": "elm_n", "name": "Elm & Oak"}
        assert [t["trip_id"] for t in result["trips"]][:1] == ["BU:2"]
        assert result["trips"][0]["depart"]["stop_id"] == "elm_n"

    def test_same_place_twice_is_a_bad_request(self, ctx):
        with pytest.raises(BadRequest):
            queries.plan(ctx, "elm_n", "elm_s", local(*WEDNESDAY, 8))


def search(ctx, **kwargs):
    return [p["id"] for p in queries.search_places(ctx, **kwargs)["places"]]


class TestSearch:
    def test_by_name(self, ctx):
        assert set(search(ctx, q="elm")) == {"elm_n", "elm_far"}
        assert search(ctx, q="hub") == ["hub"]

    def test_every_word_must_match_in_any_order(self, ctx):
        assert set(search(ctx, q="oak elm")) == {"elm_n", "elm_far"}
        assert search(ctx, q="hub far") == []

    def test_fuzzy(self, ctx):
        assert set(search(ctx, q="statoin")) == {"hub", "far"}

    def test_prefix_matches_first(self, ctx):
        assert search(ctx, q="far")[0] == "far"

    def test_agency_filter(self, ctx):
        assert set(search(ctx, q="station", agency="RA")) == {"hub", "far"}
        assert search(ctx, q="corner", agency="RA") == []
        assert search(ctx, q="corner", agency="RA,BU") == ["corner"]

    def test_places_without_service_are_not_found(self, ctx):
        assert search(ctx, q="lonely") == []

    def test_near(self, ctx):
        found = queries.search_places(ctx, near="37.6101,-122.3001", radius="500")["places"]
        assert [p["id"] for p in found] == ["elm_n"]
        assert found[0]["distance_m"] < 30
        nearest = search(ctx, near="37.70,-122.40", radius="5000")
        assert nearest[0] == "hub"

    def test_near_with_q_only_orders(self, ctx):
        assert search(ctx, q="elm", near="37.9,-122.6") == ["elm_far", "elm_n"]

    @pytest.mark.parametrize(
        "kwargs",
        [
            {},
            {"q": "e"},
            {"q": "&"},
            {"near": "north"},
            {"near": "91,0"},
            {"near": "1,1", "radius": "0"},
        ],
    )
    def test_bad_requests(self, ctx, kwargs):
        with pytest.raises(BadRequest):
            queries.search_places(ctx, **kwargs)


class TestPlaceDicts:
    def test_shape(self, ctx):
        [hub] = queries.place_dicts([Place.objects.get(feed=ctx.feed, place_id="hub")])
        assert hub["agencies"] == ["BU", "RA"]
        assert [r["id"] for r in hub["routes"]] == ["BU:1", "RA:CC", "RA:L"]
        assert hub["routes"][0]["agency"] == "BU"
        assert {p["id"] for p in hub["platforms"]} == {"hub_rail", "hub_bay"}

    def test_find_by_member_stop(self, ctx):
        assert queries.find_place(ctx, "hub_rail").place_id == "hub"
        with pytest.raises(NotFound):
            queries.find_place(ctx, "atlantis")


class TestStations:
    def test_multi_agency_feed_needs_a_filter(self, ctx):
        with pytest.raises(BadRequest) as exc:
            queries.stations(ctx)
        assert exc.value.code == "filter_required"

    def test_by_agency_in_line_order(self, ctx):
        assert [s["id"] for s in queries.stations(ctx, agency="RA")] == ["hub", "far"]

    def test_by_route(self, ctx):
        # A bus route's spokes have no meaningful order; just the right places.
        ids = {s["id"] for s in queries.stations(ctx, route="BU:1")}
        assert ids == {"elm_far", "hub", "elm_n", "corner"}


def test_agencies(ctx):
    by_id = {a["id"]: a for a in queries.agencies(ctx)}
    assert set(by_id) == {"RA", "BU", "XX"}
    assert by_id["RA"]["route_types"] == [0, 5]


class TestApi:
    def test_places(self, ctx, client):
        response = client.get("/api/v1/operators/TT/places", {"q": "hub"})
        assert response.status_code == 200
        [hub] = response.json()["places"]
        assert hub["id"] == "hub"
        assert "distance_m" not in hub

    def test_place_by_member_stop(self, ctx, client):
        assert client.get("/api/v1/operators/TT/places/elm_s").json()["id"] == "elm_n"
        assert client.get("/api/v1/operators/TT/places/nope").status_code == 404

    def test_stations_needs_a_filter(self, ctx, client):
        response = client.get("/api/v1/operators/TT/stations")
        assert response.status_code == 400
        assert response.json()["code"] == "filter_required"
        ra = client.get("/api/v1/operators/TT/stations", {"agency": "RA"}).json()
        assert [s["id"] for s in ra] == ["hub", "far"]

    def test_agencies_and_filtered_routes(self, ctx, client):
        assert len(client.get("/api/v1/operators/TT/agencies").json()) == 3
        routes = client.get("/api/v1/operators/TT/routes", {"agency": "BU"}).json()
        assert [(r["id"], r["agency"]) for r in routes] == [("BU:1", "BU")]
        operators = client.get("/api/v1/operators").json()
        assert operators[0]["agencies"] == ["BU", "RA", "XX"]
