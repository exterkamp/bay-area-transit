import pytest
from django.test import Client


@pytest.fixture
def client(feed):
    return Client()


def get(client, path, status=200):
    response = client.get(path)
    assert response.status_code == status, response.content
    return response.json()


def test_healthz(db):
    assert Client().get("/healthz").json() == {"status": "ok"}


def test_operators(client):
    [op] = get(client, "/api/v1/operators")
    assert op["code"] == "TT"
    assert op["feed"]["version"] == "v1"
    assert op["feed"]["end_date"] == "2027-12-31"
    assert op["realtime"] == {
        "trip_updates_at": None,
        "vehicle_positions_at": None,
        "alerts_at": None,
    }


def test_operator_code_is_case_insensitive(client):
    assert len(get(client, "/api/v1/operators/tt/stations")) == 3


def test_unknown_operator(client):
    error = get(client, "/api/v1/operators/XX/stations", 404)
    assert "unknown operator" in error["detail"]
    assert error["code"] == "not_found"


def test_no_active_feed_has_its_own_code(operator):
    error = get(Client(), "/api/v1/operators/TT/stations", 404)
    assert error["code"] == "no_active_feed"


def test_routes(client):
    routes = get(client, "/api/v1/operators/TT/routes")
    assert {r["id"]: r["color"] for r in routes} == {"EXP": "#e31837", "LOC": "#99d7dc"}


def test_shapes_are_geojson(client):
    shapes = get(client, "/api/v1/operators/TT/shapes")
    assert shapes["type"] == "FeatureCollection"
    [feature] = shapes["features"]
    assert feature["geometry"]["coordinates"][0] == [-122.1, 37.4]
    assert feature["properties"] == {"route_id": "LOC", "color": "#99d7dc", "agency": "TT"}


def test_plan(client):
    result = get(client, "/api/v1/operators/TT/plan?from=south&to=north&at=2026-10-28T07:55")
    assert result["at"] == "2026-10-28T07:55:00-07:00"
    assert result["trips"][0]["trip_id"] == "T1"


def test_plan_accepts_offsets(client):
    result = get(
        client, "/api/v1/operators/TT/plan?from=south&to=north&at=2026-10-28T14:55:00%2B00:00"
    )
    assert result["at"] == "2026-10-28T07:55:00-07:00"


@pytest.mark.parametrize(
    "query",
    [
        "from=south&to=south",
        "to=north",
        "from=south&to=north&at=yesterday",
        "from=south&to=north&limit=500",
    ],
)
def test_plan_bad_requests(client, query):
    get(client, f"/api/v1/operators/TT/plan?{query}", 400)


def test_departures(client):
    board = get(client, "/api/v1/operators/TT/stations/mid/departures?at=2026-10-28T08:00")
    assert board["station"] == {"id": "mid", "name": "Mid"}
    assert board["departures"][0]["destination"]["id"] == "north"


def test_trip(client):
    trip = get(client, "/api/v1/operators/TT/trips/T1?date=2026-10-28")
    assert len(trip["stops"]) == 3
    get(client, "/api/v1/operators/TT/trips/T1?date=2026-10-24", 404)
    get(client, "/api/v1/operators/TT/trips/T1?date=soon", 400)


def test_realtime_endpoints_empty_without_data(client):
    assert get(client, "/api/v1/operators/TT/vehicles") == []
    assert get(client, "/api/v1/operators/TT/alerts") == []


def test_api_is_read_only(client):
    assert client.post("/api/v1/operators").status_code == 405
