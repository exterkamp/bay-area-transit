"""Read-side queries behind the API: stations, trip planning, boards, trips.

Everything takes an operator's active feed and returns plain dicts shaped
like docs/api.md, so views stay thin and tests can call these directly.
"""

import math
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from django.contrib.gis.geos import Point
from django.contrib.postgres.aggregates import ArrayAgg
from django.core.cache import cache
from django.db import connection
from django.db.models import Max, Min, Q
from django.utils import timezone

from transit.gtfs.calendar import active_service_ids
from transit.gtfs.times import secs_since_service_start, to_datetime
from transit.models import (
    Accessibility,
    Agency,
    FareRule,
    Feed,
    LocationType,
    Operator,
    PickupDropOff,
    Place,
    RealtimeKind,
    Route,
    Shape,
    Stop,
    StopTime,
    Trip,
    TripRelationship,
    TripUpdate,
    VehiclePosition,
    VehicleStatus,
)
from transit.realtime import estimate
from transit.realtime.overlay import Call, Estimate, RealtimeIndex, TripRealtime, is_fresh

# Look this far before ``at`` in the schedule, so a late train scheduled to
# have left already still shows up if realtime says it hasn't.
LATE_TRAIN_WINDOW = timedelta(minutes=30)

ACCESSIBILITY_NAMES = {
    Accessibility.UNKNOWN: "unknown",
    Accessibility.ACCESSIBLE: "accessible",
    Accessibility.INACCESSIBLE: "inaccessible",
}


class NotFound(Exception):
    def __init__(self, message, code="not_found"):
        super().__init__(message)
        self.code = code


class BadRequest(Exception):
    def __init__(self, message, code="bad_request"):
        super().__init__(message)
        self.code = code


@dataclass
class Context:
    operator: Operator
    feed: Feed

    @property
    def tz(self):
        return ZoneInfo(self.operator.timezone)


def context_for(code: str) -> Context:
    operator = Operator.objects.filter(code=code.upper()).first()
    if operator is None:
        raise NotFound(f"unknown operator {code!r}")
    feed = operator.active_feed
    if feed is None:
        raise NotFound(f"{operator.code} has no active feed yet", code="no_active_feed")
    return Context(operator, feed)


def iso(moment: datetime | None, tz) -> str | None:
    return moment.astimezone(tz).isoformat() if moment else None


def hex_color(value, default):
    return f"#{value.lower()}" if value else default


def route_dict(route):
    return {
        "id": route.route_id,
        "short_name": route.short_name or route.long_name,
        "color": hex_color(route.color, "#888888"),
        "text_color": hex_color(route.text_color, "#000000"),
        "agency": route.agency.agency_id,
        "type": route.route_type,
    }


# --- places -------------------------------------------------------------------------

SEARCH_MIN_CHARS = 2
NEAR_RADIUS = 1000
NEAR_MAX_RADIUS = 5000
# pg_trgm word_similarity a search word needs to count as a fuzzy match.
# Shorter words must appear as written: three letters share half their
# trigrams with too many names ("elm" and "Elsewhere").
WORD_MATCH = 0.5
FUZZY_MIN_CHARS = 4


def _place_ref(stop: Stop) -> dict:
    """{"id", "name"} of the place a stop belongs to."""
    place = stop.place if stop.place_id else None
    if place is None:
        # Boarding areas and the like belong to no place; name the stop itself.
        return {"id": stop.stop_id, "name": stop.name}
    return {"id": place.place_id, "name": place.name}


def agencies(ctx: Context) -> list[dict]:
    types = {}
    for agency_pk, route_type in (
        Route.objects.filter(feed=ctx.feed).values_list("agency_id", "route_type").distinct()
    ):
        types.setdefault(agency_pk, set()).add(route_type)
    return [
        {
            "id": a.agency_id,
            "name": a.name,
            "url": a.url,
            "timezone": a.timezone,
            "route_types": sorted(types.get(a.pk, ())),
        }
        for a in Agency.objects.filter(feed=ctx.feed).order_by("agency_id")
    ]


def agency_ids(value) -> list[str]:
    return [a.strip() for a in (value or "").split(",") if a.strip()]


def place_dicts(places, distances=None) -> list[dict]:
    """Full place dicts, with routes and platforms loaded in two queries."""
    pks = [p.pk for p in places]
    routes = {}
    links = Place.routes.through.objects.filter(place_id__in=pks).select_related("route__agency")
    for link in links:
        routes.setdefault(link.place_id, []).append(link.route)
    platforms = {}
    for stop in Stop.objects.filter(place_id__in=pks, location_type=LocationType.STOP).order_by(
        "stop_id"
    ):
        platforms.setdefault(stop.place_id, []).append(stop)
    result = []
    for place in places:
        served = sorted(
            routes.get(place.pk, []),
            key=lambda r: (r.agency.agency_id, r.sort_order or 0, r.short_name or r.long_name),
        )
        item = {
            "id": place.place_id,
            "name": place.name,
            "kind": place.kind,
            "lat": place.lat,
            "lon": place.lon,
            "zone": place.zone_id,
            "wheelchair_boarding": ACCESSIBILITY_NAMES[place.wheelchair_boarding],
            "agencies": sorted({r.agency.agency_id for r in served}),
            "routes": [route_dict(r) for r in served],
            "platforms": [
                {"id": p.stop_id, "name": p.name, "platform_code": p.platform_code}
                for p in platforms.get(place.pk, [])
            ],
        }
        if distances is not None:
            item["distance_m"] = round(distances[place.pk])
        result.append(item)
    return result


def find_place(ctx: Context, place_id: str) -> Place:
    """A place by its id, or by the stop_id of any stop in it."""
    place = Place.objects.filter(feed=ctx.feed, place_id=place_id).first()
    if place is None:
        stop = (
            Stop.objects.filter(feed=ctx.feed, stop_id=place_id, place__isnull=False)
            .select_related("place")
            .first()
        )
        place = stop and stop.place
    if place is None:
        raise NotFound(f"unknown place {place_id!r}")
    return place


def search_places(ctx: Context, q=None, near=None, radius=None, agency=None, limit=None):
    limit = _parse_limit(limit, 20)
    words = re.findall(r"\w+", (q or "").casefold())
    if q is not None and len("".join(words)) < SEARCH_MIN_CHARS:
        raise BadRequest(f"q needs at least {SEARCH_MIN_CHARS} letters or digits")
    if not words and near is None:
        raise BadRequest("give q, near, or both")
    point = _parse_near(near) if near is not None else None
    radius = _parse_radius(radius)

    sql = [f'SELECT p.id FROM "{Place._meta.db_table}" p WHERE p.feed_id = %s']
    params = [ctx.feed.pk]
    sql.append(
        f"""AND EXISTS (SELECT 1 FROM "{Place.routes.through._meta.db_table}" pr
        JOIN "{Route._meta.db_table}" r ON r.id = pr.route_id
        JOIN "{Agency._meta.db_table}" a ON a.id = r.agency_id
        WHERE pr.place_id = p.id {"AND a.agency_id = ANY(%s)" if agency else ""})"""
    )
    if agency:
        params.append(agency_ids(agency))
    score = []
    for word in words:
        # Every word must appear, as a substring or a close fuzzy match.
        if len(word) >= FUZZY_MIN_CHARS:
            sql.append("AND (p.name ILIKE %s OR word_similarity(%s, p.name) >= %s)")
            params += [f"%{word}%", word, WORD_MATCH]
        else:
            sql.append("AND p.name ILIKE %s")
            params.append(f"%{word}%")
        score.append("word_similarity(%s, p.name)")
    score_params = list(words)
    if point is not None:
        geography = "ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography"
        distance = f"ST_Distance(p.point::geography, {geography})"
        if not words:
            sql.append(f"AND ST_DWithin(p.point::geography, {geography}, %s)")
            params += [point[1], point[0], radius]
        order = f"{distance}, p.name"
        order_params = [point[1], point[0]]
    else:
        prefix = "(lower(p.name) LIKE %s)"
        # Equally good matches: stations before street stops, then names that
        # start with the first word, then shorter names.
        order = (
            f"({' + '.join(score)}) DESC, (p.kind = 'station') DESC, {prefix} DESC, "
            "length(p.name), p.name"
        )
        order_params = [f"{words[0]}%", *score_params]
    query = " ".join(sql) + f" ORDER BY {order} LIMIT %s"
    with connection.cursor() as cursor:
        cursor.execute(query, [*params, *order_params, limit])
        pks = [row[0] for row in cursor.fetchall()]

    places = Place.objects.in_bulk(pks)
    ordered = [places[pk] for pk in pks]
    distances = None
    if point is not None:
        here = Point(point[1], point[0], srid=4326)
        distances = {p.pk: _meters(here, p.point) for p in ordered}
    return {"places": place_dicts(ordered, distances)}


def _parse_near(value):
    try:
        lat, lon = (float(part) for part in value.split(","))
    except ValueError:
        raise BadRequest("near must be lat,lon") from None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise BadRequest("near is out of range")
    return lat, lon


def _parse_radius(value):
    if value in (None, ""):
        return NEAR_RADIUS
    try:
        radius = int(value)
    except ValueError:
        raise BadRequest("radius must be an integer") from None
    if not 1 <= radius <= NEAR_MAX_RADIUS:
        raise BadRequest(f"radius must be between 1 and {NEAR_MAX_RADIUS}")
    return radius


def _meters(a, b):
    """Great-circle distance in meters between two lon/lat points."""
    lat1, lat2 = math.radians(a.y), math.radians(b.y)
    dlat, dlon = lat2 - lat1, math.radians(b.x - a.x)
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * 6_371_000 * math.asin(math.sqrt(h))


# --- stations (places in line order) -----------------------------------------------


def stations(ctx: Context, agency=None, route=None) -> list[dict]:
    trips = Trip.objects.filter(feed=ctx.feed)
    if agency:
        trips = trips.filter(route__agency__agency_id__in=agency_ids(agency))
    if route:
        trips = trips.filter(route__route_id=route)
    if not agency and not route and Agency.objects.filter(feed=ctx.feed).count() > 1:
        raise BadRequest(
            "this feed has several agencies: filter by agency or route, or search places",
            code="filter_required",
        )
    order = _line_order(ctx.feed, trips)
    places = Place.objects.in_bulk(order)
    return place_dicts([places[pk] for pk in order])


def _line_order(feed, trips) -> list[int]:
    """Place pks served by ``trips``, in line order, north end first.

    Every distinct stopping pattern contributes "A comes before B" edges, all
    oriented the same way as the longest pattern, and a topological sort merges
    them. That places branch and short-turn stations (Caltrain's South County
    stops past Tamien) where they belong instead of at the end of the list.
    Ties, and anything a loop route makes unsortable, follow the longest
    pattern, then latitude.
    """
    patterns = set()
    rows = (
        StopTime.objects.filter(feed=feed, trip__in=trips, stop__place__isnull=False)
        .values("trip_id")
        .annotate(places=ArrayAgg("stop__place_id", order_by="stop_sequence"))
        .values_list("places", flat=True)
    )
    for places in rows:
        seq = []
        for pk in places:
            if pk not in seq:
                seq.append(pk)
        patterns.add(tuple(seq))
    distinct = sorted(patterns, key=lambda p: (-len(p), p))
    if not distinct:
        return []
    lat = {
        pk: point.y
        for pk, point in Place.objects.filter(
            pk__in={pk for p in distinct for pk in p}
        ).values_list("pk", "point")
    }
    reference = list(distinct[0])
    rank = {pk: i for i, pk in enumerate(reference)}

    edges = {}
    indegree = {}
    for pattern in distinct:
        shared = [rank[pk] for pk in pattern if pk in rank]
        if len(shared) >= 2 and shared[0] > shared[-1]:
            pattern = pattern[::-1]
        for pk in pattern:
            indegree.setdefault(pk, 0)
        for a, b in zip(pattern, pattern[1:], strict=False):
            if b not in edges.setdefault(a, set()):
                edges[a].add(b)
                indegree[b] += 1

    def priority(pk):
        return (rank.get(pk, len(rank)), -lat[pk])

    order = []
    ready = sorted((pk for pk, n in indegree.items() if n == 0), key=priority)
    while ready:
        pk = ready.pop(0)
        order.append(pk)
        for nxt in edges.get(pk, ()):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                ready.append(nxt)
        ready.sort(key=priority)
    placed = set(order)
    order += sorted((pk for pk in indegree if pk not in placed), key=priority)

    if lat[order[0]] < lat[order[-1]]:
        order.reverse()
    return order


def _boarding_stop_pks(place: Place) -> set[int]:
    """Where you can actually board at a place: its stops, not the station node."""
    pks = set(place.stops.filter(location_type=LocationType.STOP).values_list("pk", flat=True))
    return pks or set(place.stops.values_list("pk", flat=True))


# --- schedule search ----------------------------------------------------------------


@dataclass
class Leg:
    """One scheduled trip through a station on one service date."""

    trip_pk: int
    service_date: date
    board_seq: int
    board_stop_pk: int
    board_secs: int
    alight_seq: int | None = None
    alight_stop_pk: int | None = None


def _search_dates(ctx, at):
    """Service dates a departure at/after ``at`` could belong to, oldest first."""
    today = at.astimezone(ctx.tz).date()
    return [today - timedelta(days=1), today, today + timedelta(days=1)]


def _boardings(ctx, stop_pks, at, service_date):
    services = active_service_ids(ctx.feed, service_date)
    if not services:
        return []
    earliest = secs_since_service_start(at - LATE_TRAIN_WINDOW, service_date, ctx.tz)
    rows = (
        StopTime.objects.filter(
            feed=ctx.feed,
            stop_id__in=stop_pks,
            trip__service_id__in=services,
            departure_secs__gte=max(earliest, 0),
        )
        .exclude(pickup_type=PickupDropOff.NONE)
        .values_list("trip_id", "stop_sequence", "stop_id", "departure_secs")
    )
    return [Leg(t, service_date, seq, stop, secs) for t, seq, stop, secs in rows]


@dataclass
class TripData:
    """Everything needed to render trips: the trip, its calls and their realtime."""

    trips: dict
    calls: dict  # trip pk -> [CallRow], in sequence order
    realtime: dict  # (trip pk, service date) -> TripRealtime


@dataclass(slots=True)
class CallRow:
    """A stop time as the read side uses it.

    A board at a busy station loads every call of a few hundred trips, and
    full StopTime instances (each with its stop, place and two geometries)
    cost a hundred times more than the query that fetches them.
    """

    stop_sequence: int
    arrival_secs: int | None
    departure_secs: int | None
    stop: Stop


def _load(ctx, legs) -> TripData:
    trip_pks = {leg.trip_pk for leg in legs}
    trips = Trip.objects.filter(pk__in=trip_pks).select_related("route__agency").in_bulk()
    rows = list(
        StopTime.objects.filter(trip_id__in=trip_pks)
        .order_by("trip_id", "stop_sequence")
        .values_list("trip_id", "stop_sequence", "arrival_secs", "departure_secs", "stop_id")
    )
    stops = (
        Stop.objects.filter(pk__in={row[4] for row in rows})
        .select_related("place")
        .defer("point", "desc", "place__point")
        .in_bulk()
    )
    calls = {}
    for trip_pk, seq, arrival, departure, stop_pk in rows:
        calls.setdefault(trip_pk, []).append(CallRow(seq, arrival, departure, stops[stop_pk]))
    index = RealtimeIndex(ctx.operator, [t.trip_id for t in trips.values()])
    realtime = {}
    for leg in legs:
        key = (leg.trip_pk, leg.service_date)
        if key in realtime:
            continue
        trip_id = trips[leg.trip_pk].trip_id
        if not index.covers(trip_id):
            realtime[key] = TripRealtime()
        else:
            realtime[key] = index.for_trip(
                trip_id,
                leg.service_date,
                _calls(ctx, calls[leg.trip_pk], leg.service_date),
            )
    return TripData(trips, calls, realtime)


def _calls(ctx, stop_times, service_date) -> list[Call]:
    return [
        Call(
            st.stop_sequence,
            st.stop.stop_id,
            to_datetime(service_date, st.arrival_secs, ctx.tz)
            if st.arrival_secs is not None
            else None,
            to_datetime(service_date, st.departure_secs, ctx.tz)
            if st.departure_secs is not None
            else None,
        )
        for st in stop_times
    ]


def _time_dict(ctx, scheduled_secs, service_date, estimated, delay):
    scheduled = (
        to_datetime(service_date, scheduled_secs, ctx.tz) if scheduled_secs is not None else None
    )
    return {
        "scheduled": iso(scheduled, ctx.tz),
        "estimated": iso(estimated, ctx.tz),
        "delay_seconds": delay,
    }


def _endpoint(ctx, st, service_date, prediction: Estimate, which):
    secs = st.departure_secs if which == "departure" else st.arrival_secs
    est = prediction.departure if which == "departure" else prediction.arrival
    delay = prediction.departure_delay if which == "departure" else prediction.arrival_delay
    return {
        "stop_id": st.stop.stop_id,
        "platform": st.stop.name,
        **_time_dict(ctx, secs, service_date, est, delay),
    }


def _status(rt: TripRealtime, *estimates):
    if rt.status == "canceled" or any(e.skipped for e in estimates):
        return "canceled"
    return rt.status


def _trip_summary(trip, service_date, status):
    return {
        "trip_id": trip.trip_id,
        "service_date": service_date.isoformat(),
        "short_name": trip.short_name or trip.trip_id,
        "headsign": trip.headsign,
        "direction": trip.direction_id,
        "route": route_dict(trip.route),
        "status": status,
    }


def _effective_departure(ctx, leg, rt: TripRealtime):
    est = rt.at(leg.board_seq)
    return est.departure or to_datetime(leg.service_date, leg.board_secs, ctx.tz)


def _parse_limit(limit, default, maximum=50):
    if limit in (None, ""):
        return default
    try:
        value = int(limit)
    except (TypeError, ValueError):
        raise BadRequest("limit must be an integer") from None
    if not 1 <= value <= maximum:
        raise BadRequest(f"limit must be between 1 and {maximum}")
    return value


def plan(ctx: Context, from_id, to_id, at: datetime, limit=None) -> dict:
    limit = _parse_limit(limit, 10)
    if not from_id or not to_id:
        raise BadRequest("from and to are required")
    origin, destination = find_place(ctx, from_id), find_place(ctx, to_id)
    if origin.pk == destination.pk:
        raise BadRequest("from and to must be different places")
    to_pks = _boarding_stop_pks(destination)

    legs = []
    for service_date in _search_dates(ctx, at):
        found = _boardings(ctx, _boarding_stop_pks(origin), at, service_date)
        if not found:
            continue
        alights = {}
        for trip_pk, seq, stop_pk in (
            StopTime.objects.filter(trip_id__in={leg.trip_pk for leg in found}, stop_id__in=to_pks)
            .exclude(drop_off_type=PickupDropOff.NONE)
            .values_list("trip_id", "stop_sequence", "stop_id")
        ):
            alights.setdefault(trip_pk, []).append((seq, stop_pk))
        for leg in found:
            later = sorted(a for a in alights.get(leg.trip_pk, []) if a[0] > leg.board_seq)
            if later:
                leg.alight_seq, leg.alight_stop_pk = later[0]
                legs.append(leg)

    data = _load(ctx, legs)
    rows = []
    for leg in legs:
        rt = data.realtime[(leg.trip_pk, leg.service_date)]
        departs = _effective_departure(ctx, leg, rt)
        if departs < at:
            continue
        rows.append((departs, leg, rt))
    rows.sort(key=lambda r: (r[0], r[1].trip_pk))
    rows = rows[:limit]

    trips = []
    fare = None
    for _, leg, rt in rows:
        trip = data.trips[leg.trip_pk]
        by_seq = {st.stop_sequence: st for st in data.calls[leg.trip_pk]}
        board, alight = by_seq[leg.board_seq], by_seq[leg.alight_seq]
        board_est, alight_est = rt.at(leg.board_seq), rt.at(leg.alight_seq)
        scheduled_minutes = (alight.arrival_secs - board.departure_secs) // 60
        trips.append(
            {
                **_trip_summary(trip, leg.service_date, _status(rt, board_est, alight_est)),
                "depart": _endpoint(ctx, board, leg.service_date, board_est, "departure"),
                "arrive": _endpoint(ctx, alight, leg.service_date, alight_est, "arrival"),
                "duration_minutes": scheduled_minutes,
                "stops_between": sum(1 for seq in by_seq if leg.board_seq < seq < leg.alight_seq),
            }
        )
        if fare is None:
            fare = fare_between(ctx, board.stop, alight.stop, trip.route_id)

    return {
        "from": {"id": origin.place_id, "name": origin.name},
        "to": {"id": destination.place_id, "name": destination.name},
        "at": iso(at, ctx.tz),
        "fare": fare,
        "trips": trips,
    }


def departures(ctx: Context, station_id, at: datetime, limit=None) -> dict:
    limit = _parse_limit(limit, 20)
    station = find_place(ctx, station_id)
    stop_pks = _boarding_stop_pks(station)
    legs = []
    for service_date in _search_dates(ctx, at):
        legs.extend(_boardings(ctx, stop_pks, at, service_date))

    last_seq = dict(
        StopTime.objects.filter(trip_id__in={leg.trip_pk for leg in legs})
        .values("trip_id")
        .annotate(last=Max("stop_sequence"))
        .values_list("trip_id", "last")
    )
    legs = [leg for leg in legs if leg.board_seq < last_seq[leg.trip_pk]]
    data = _load(ctx, legs)
    rows = []
    for leg in legs:
        rt = data.realtime[(leg.trip_pk, leg.service_date)]
        departs = _effective_departure(ctx, leg, rt)
        if departs >= at:
            rows.append((departs, leg, rt))
    rows.sort(key=lambda r: (r[0], r[1].trip_pk))

    result = []
    for _, leg, rt in rows[:limit]:
        trip = data.trips[leg.trip_pk]
        calls = data.calls[leg.trip_pk]
        board = next(st for st in calls if st.stop_sequence == leg.board_seq)
        est = rt.at(leg.board_seq)
        result.append(
            {
                **_trip_summary(trip, leg.service_date, _status(rt, est)),
                "depart": _endpoint(ctx, board, leg.service_date, est, "departure"),
                "destination": _place_ref(calls[-1].stop),
            }
        )
    return {
        "station": {"id": station.place_id, "name": station.name},
        "at": iso(at, ctx.tz),
        "departures": result,
    }


def trip_detail(ctx: Context, trip_id, service_date: date, now=None) -> dict:
    trip = (
        Trip.objects.filter(feed=ctx.feed, trip_id=trip_id).select_related("route__agency").first()
    )
    if trip is None:
        raise NotFound(f"unknown trip {trip_id!r}")
    if trip.service_id not in active_service_ids(ctx.feed, service_date):
        raise NotFound(f"trip {trip_id!r} does not run on {service_date}")
    first = StopTime.objects.filter(trip=trip).order_by("stop_sequence").first()
    leg = Leg(trip.pk, service_date, first.stop_sequence, first.stop_id, first.departure_secs or 0)
    data = _load(ctx, [leg])
    rt = data.realtime[(trip.pk, service_date)]

    stops = []
    for st in data.calls[trip.pk]:
        est = rt.at(st.stop_sequence)
        place = _place_ref(st.stop)
        stops.append(
            {
                "sequence": st.stop_sequence,
                "stop_id": st.stop.stop_id,
                "station_id": place["id"],
                "name": place["name"],
                "arrival": _time_dict(
                    ctx, st.arrival_secs, service_date, est.arrival, est.arrival_delay
                ),
                "departure": _time_dict(
                    ctx, st.departure_secs, service_date, est.departure, est.departure_delay
                ),
                "skipped": est.skipped,
            }
        )
    vehicle = next(iter(vehicles(ctx, trip_ids=[trip.trip_id], now=now)), None)
    return {
        **_trip_summary(trip, service_date, rt.status),
        "bikes_allowed": trip.bikes_allowed == Accessibility.ACCESSIBLE,
        "wheelchair_accessible": trip.wheelchair_accessible == Accessibility.ACCESSIBLE,
        "stops": stops,
        "vehicle": vehicle,
    }


# --- fares --------------------------------------------------------------------------


def fare_between(ctx, board: Stop, alight: Stop, route_pk) -> dict | None:
    """Cheapest fare_rules match for a ride, preferring zone rules over flat fares."""
    origin = board.zone_id or (board.place.zone_id if board.place_id else "")
    dest = alight.zone_id or (alight.place.zone_id if alight.place_id else "")
    rules = FareRule.objects.filter(feed=ctx.feed, contains_id="").filter(
        Q(route__isnull=True) | Q(route_id=route_pk)
    )
    for candidates in (
        rules.filter(origin_id=origin, destination_id=dest) if origin and dest else None,
        rules.filter(origin_id="", destination_id=""),
    ):
        if candidates is None:
            continue
        rule = candidates.select_related("fare").order_by("fare__price").first()
        if rule:
            return {"price": str(rule.fare.price), "currency": rule.fare.currency_type}
    return None


# --- realtime views -----------------------------------------------------------------

_VEHICLE_STATUS = {
    VehicleStatus.INCOMING_AT: "incoming_at",
    VehicleStatus.STOPPED_AT: "stopped_at",
    VehicleStatus.IN_TRANSIT_TO: "in_transit_to",
}


# Every map polls /vehicles, and estimating positions costs a few hundred
# milliseconds. In this long an estimate moves a few hundred meters at most.
VEHICLES_CACHE_SECONDS = 10


def vehicles(ctx: Context, trip_ids=None, agency=None, now=None) -> list[dict]:
    """GPS positions, plus estimated ones for live trips that have no GPS.

    Computed for the whole feed and cached for VEHICLES_CACHE_SECONDS, then
    filtered, unless a fixed ``now`` is given (tests).
    """
    if now is not None:
        return _vehicles(ctx, trip_ids, agency, now)
    key = f"vehicles:{ctx.feed.pk}"
    everything = cache.get(key)
    if everything is None:
        everything = _vehicles(ctx, None, None, timezone.now())
        cache.set(key, everything, VEHICLES_CACHE_SECONDS)
    wanted = set(agency_ids(agency))
    return [
        v
        for v in everything
        if (trip_ids is None or v["trip_id"] in trip_ids)
        and (not wanted or (v["route"] is not None and v["route"]["agency"] in wanted))
    ]


def _vehicles(ctx, trip_ids, agency, now) -> list[dict]:
    gps = []
    if is_fresh(ctx.operator, RealtimeKind.VEHICLE_POSITIONS):
        gps = _gps_vehicles(ctx, trip_ids, agency)
    estimated = []
    if is_fresh(ctx.operator, RealtimeKind.TRIP_UPDATES):
        covered = {v["trip_id"] for v in gps if v["trip_id"]}
        estimated = _estimated_vehicles(ctx, trip_ids, agency, now, covered)
    return gps + estimated


def _gps_vehicles(ctx, trip_ids, agency) -> list[dict]:
    positions = VehiclePosition.objects.filter(operator=ctx.operator)
    if trip_ids is not None:
        positions = positions.filter(trip_id__in=trip_ids)
    if agency:
        positions = positions.filter(
            trip_id__in=Trip.objects.filter(
                feed=ctx.feed, route__agency__agency_id__in=agency_ids(agency)
            ).values("trip_id")
        )
    positions = list(positions.order_by("trip_id", "vehicle_id"))
    trips = {
        t.trip_id: t
        for t in Trip.objects.filter(
            feed=ctx.feed, trip_id__in={p.trip_id for p in positions if p.trip_id}
        ).select_related("route__agency")
    }
    result = []
    for p in positions:
        trip = trips.get(p.trip_id)
        result.append(
            {
                "vehicle_id": p.vehicle_id or p.label or None,
                "trip_id": p.trip_id or None,
                "short_name": (trip.short_name or trip.trip_id) if trip else None,
                "route": route_dict(trip.route) if trip else None,
                "headsign": trip.headsign if trip else None,
                "lat": p.point.y,
                "lon": p.point.x,
                "bearing": p.bearing,
                "status": _VEHICLE_STATUS.get(p.current_status),
                "stop_id": p.stop_id or None,
                "timestamp": iso(p.timestamp, ctx.tz),
                "source": "gps",
            }
        )
    return result


# How far off schedule a trip can run and still be placed from its predictions.
EARLY_SLACK = timedelta(minutes=10)
LATE_SLACK = timedelta(hours=1)


def _estimated_vehicles(ctx, trip_ids, agency, now, covered) -> list[dict]:
    updates = TripUpdate.objects.filter(operator=ctx.operator).exclude(
        schedule_relationship__in=[TripRelationship.CANCELED, TripRelationship.DELETED]
    )
    if trip_ids is not None:
        updates = updates.filter(trip_id__in=trip_ids)
    vehicle_of = {
        trip_id: vehicle_id
        for trip_id, vehicle_id in updates.values_list("trip_id", "vehicle_id")
        if trip_id not in covered
    }
    # BART fills vehicle.id with a car type ("3-door"), the same for many
    # trains. An id that isn't unique identifies nothing.
    shared = {v for v, n in Counter(vehicle_of.values()).items() if n > 1}
    vehicle_of = {t: ("" if v in shared else v) for t, v in vehicle_of.items()}
    trips = Trip.objects.filter(feed=ctx.feed, trip_id__in=vehicle_of).select_related(
        "route__agency"
    )
    if agency:
        trips = trips.filter(route__agency__agency_id__in=agency_ids(agency))
    trips = list(trips)
    if not trips:
        return []

    # Predictions often cover trips that haven't started yet. Skip any whose
    # schedule can't be running now, before loading their stops.
    span = {
        trip_pk: (first, last)
        for trip_pk, first, last in StopTime.objects.filter(trip__in=trips)
        .values("trip_id")
        .annotate(first=Min("departure_secs"), last=Max("arrival_secs"))
        .values_list("trip_id", "first", "last")
    }
    # A trip running now belongs to today's service day or, after midnight,
    # yesterday's. Today first: it's the likelier one.
    today = now.astimezone(ctx.tz).date()
    legs = []
    for service_date in (today, today - timedelta(days=1)):
        running = active_service_ids(ctx.feed, service_date)
        secs = secs_since_service_start(now, service_date, ctx.tz)
        for t in trips:
            first, last = span.get(t.pk, (None, None))
            if t.service_id not in running or first is None or last is None:
                continue
            if first - EARLY_SLACK.total_seconds() <= secs <= last + LATE_SLACK.total_seconds():
                legs.append(Leg(t.pk, service_date, 0, 0, 0))
    if not legs:
        return []
    data = _load(ctx, legs)
    stop_points = dict(
        Stop.objects.filter(
            pk__in={c.stop.pk for calls in data.calls.values() for c in calls}
        ).values_list("pk", "point")
    )
    shapes = Shape.objects.in_bulk({t.shape_id for t in trips if t.shape_id})

    result = []
    placed = set()
    for leg in legs:
        rt = data.realtime[(leg.trip_pk, leg.service_date)]
        if rt.status != "live" or leg.trip_pk in placed:
            continue
        trip = data.trips[leg.trip_pk]
        stops = _timed_stops(ctx, data.calls[leg.trip_pk], leg.service_date, rt, stop_points)
        shape = shapes.get(trip.shape_id)
        where = estimate.place(stops, now, shape.geometry if shape else None)
        if where is None:
            continue
        placed.add(leg.trip_pk)
        result.append(
            {
                "vehicle_id": vehicle_of.get(trip.trip_id) or None,
                "trip_id": trip.trip_id,
                "short_name": trip.short_name or trip.trip_id,
                "route": route_dict(trip.route),
                "headsign": trip.headsign,
                "lat": where.point.y,
                "lon": where.point.x,
                "bearing": where.bearing,
                "status": _VEHICLE_STATUS[where.status],
                "stop_id": where.stop_id,
                "timestamp": iso(now, ctx.tz),
                "source": "estimated",
            }
        )
    result.sort(key=lambda v: v["trip_id"])
    return result


def _timed_stops(ctx, calls, service_date, rt, stop_points) -> list[estimate.TimedStop]:
    """Each call's best known times: predicted, else scheduled.

    Stops before the first prediction are behind the vehicle and get no
    estimate from the overlay; they take the first prediction's delay, so
    the segment the vehicle is on isn't stretched back to an on-time
    departure it didn't make.
    """
    delay = next(
        (
            e.departure_delay if e.departure_delay is not None else e.arrival_delay
            for e in (rt.at(c.stop_sequence) for c in calls)
            if e.departure_delay is not None or e.arrival_delay is not None
        ),
        0,
    )
    shift = timedelta(seconds=delay)
    stops = []
    predicted = False
    for c in calls:
        est = rt.at(c.stop_sequence)
        point = stop_points.get(c.stop.pk)
        if est.skipped or point is None:
            continue
        predicted = predicted or est.arrival is not None or est.departure is not None
        arrival = (
            to_datetime(service_date, c.arrival_secs, ctx.tz)
            if c.arrival_secs is not None
            else None
        )
        departure = (
            to_datetime(service_date, c.departure_secs, ctx.tz)
            if c.departure_secs is not None
            else None
        )
        if not predicted:
            arrival = arrival and arrival + shift
            departure = departure and departure + shift
        stops.append(
            estimate.TimedStop(
                c.stop_sequence,
                c.stop.stop_id,
                point,
                est.arrival or arrival,
                est.departure or departure,
            )
        )
    return stops
