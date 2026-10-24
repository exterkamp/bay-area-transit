"""Read-side queries behind the API: stations, trip planning, boards, trips.

Everything takes an operator's active feed and returns plain dicts shaped
like docs/api.md, so views stay thin and tests can call these directly.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from django.db.models import Max, Q

from transit.gtfs.calendar import active_service_ids
from transit.gtfs.times import secs_since_service_start, to_datetime
from transit.models import (
    Accessibility,
    FareRule,
    Feed,
    LocationType,
    Operator,
    PickupDropOff,
    Stop,
    StopTime,
    Trip,
    VehiclePosition,
    VehicleStatus,
)
from transit.realtime.overlay import Call, Estimate, RealtimeIndex, TripRealtime

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
    code = "bad_request"


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
    }


# --- stations ---------------------------------------------------------------------


def _station_of(stop: Stop) -> Stop:
    """The rider-facing place for a stop: its parent station, or itself."""
    return stop.parent_station if stop.parent_station_id else stop


def stations(ctx: Context) -> list[dict]:
    feed = ctx.feed
    stops = list(Stop.objects.filter(feed=feed).select_related("parent_station"))
    by_pk = {s.pk: s for s in stops}
    places = [s for s in stops if s.location_type == LocationType.STATION]
    if not places:
        # Feeds without stations: every free-standing stop is its own station.
        places = [
            s for s in stops if s.location_type == LocationType.STOP and not s.parent_station_id
        ]
    platforms = {}
    for s in stops:
        if s.location_type == LocationType.STOP and s.parent_station_id:
            platforms.setdefault(s.parent_station_id, []).append(s)

    order = _line_order(feed, by_pk)
    rank = {pk: i for i, pk in enumerate(order)}
    places.sort(key=lambda s: (rank.get(s.pk, len(rank)), s.name))
    return [
        {
            "id": s.stop_id,
            "name": s.name,
            "lat": s.lat,
            "lon": s.lon,
            "zone": s.zone_id,
            "wheelchair_boarding": ACCESSIBILITY_NAMES[s.wheelchair_boarding],
            "platforms": [
                {"id": p.stop_id, "name": p.name, "platform_code": p.platform_code}
                for p in sorted(platforms.get(s.pk, []), key=lambda p: p.stop_id)
            ],
        }
        for s in places
    ]


def _line_order(feed, by_pk) -> list[int]:
    """Station pks in line order, north end first.

    Every distinct stopping pattern contributes "A comes before B" edges, all
    oriented the same way as the longest pattern, and a topological sort merges
    them. That places branch and short-turn stations (Caltrain's South County
    stops past Tamien) where they belong instead of at the end of the list.
    Ties, and anything a loop route makes unsortable, follow the longest
    pattern, then latitude.
    """
    patterns = {}
    for trip_pk, stop_pk in (
        StopTime.objects.filter(feed=feed)
        .order_by("trip_id", "stop_sequence")
        .values_list("trip_id", "stop_id")
    ):
        station = _station_of(by_pk[stop_pk]).pk
        seq = patterns.setdefault(trip_pk, [])
        if station not in seq:
            seq.append(station)
    distinct = sorted({tuple(p) for p in patterns.values() if p}, key=len, reverse=True)
    if not distinct:
        return []
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
        return (rank.get(pk, len(rank)), -(by_pk[pk].lat or 0))

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
    order += sorted((pk for pk in indegree if pk not in order), key=priority)

    if (by_pk[order[0]].lat or 0) < (by_pk[order[-1]].lat or 0):
        order.reverse()
    return order


def find_station(ctx: Context, station_id: str) -> Stop:
    station = (
        Stop.objects.filter(feed=ctx.feed, stop_id=station_id)
        .filter(
            Q(location_type=LocationType.STATION)
            | Q(location_type=LocationType.STOP, parent_station__isnull=True)
        )
        .first()
    )
    if station is None:
        raise NotFound(f"unknown station {station_id!r}")
    return station


def _boarding_stop_pks(station: Stop) -> set[int]:
    """Where you can actually board at a station: its platforms, or the stop itself."""
    pks = set(station.children.filter(location_type=LocationType.STOP).values_list("pk", flat=True))
    return pks or {station.pk}


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
    calls: dict  # trip pk -> [StopTime], in sequence order
    realtime: dict  # (trip pk, service date) -> TripRealtime


def _load(ctx, legs) -> TripData:
    trip_pks = {leg.trip_pk for leg in legs}
    trips = Trip.objects.filter(pk__in=trip_pks).select_related("route").in_bulk()
    calls = {}
    for st in (
        StopTime.objects.filter(trip_id__in=trip_pks)
        .select_related("stop__parent_station")
        .order_by("trip_id", "stop_sequence")
    ):
        calls.setdefault(st.trip_id, []).append(st)
    index = RealtimeIndex(ctx.operator, [t.trip_id for t in trips.values()])
    realtime = {}
    for leg in legs:
        key = (leg.trip_pk, leg.service_date)
        if key not in realtime:
            realtime[key] = index.for_trip(
                trips[leg.trip_pk].trip_id,
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


def _endpoint(ctx, st, service_date, estimate: Estimate, which):
    secs = st.departure_secs if which == "departure" else st.arrival_secs
    est = estimate.departure if which == "departure" else estimate.arrival
    delay = estimate.departure_delay if which == "departure" else estimate.arrival_delay
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
    if from_id == to_id:
        raise BadRequest("from and to must be different stations")
    origin, destination = find_station(ctx, from_id), find_station(ctx, to_id)
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
        "from": {"id": origin.stop_id, "name": origin.name},
        "to": {"id": destination.stop_id, "name": destination.name},
        "at": iso(at, ctx.tz),
        "fare": fare,
        "trips": trips,
    }


def departures(ctx: Context, station_id, at: datetime, limit=None) -> dict:
    limit = _parse_limit(limit, 20)
    station = find_station(ctx, station_id)
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
        end = _station_of(calls[-1].stop)
        est = rt.at(leg.board_seq)
        result.append(
            {
                **_trip_summary(trip, leg.service_date, _status(rt, est)),
                "depart": _endpoint(ctx, board, leg.service_date, est, "departure"),
                "destination": {"id": end.stop_id, "name": end.name},
            }
        )
    return {
        "station": {"id": station.stop_id, "name": station.name},
        "at": iso(at, ctx.tz),
        "departures": result,
    }


def trip_detail(ctx: Context, trip_id, service_date: date) -> dict:
    trip = Trip.objects.filter(feed=ctx.feed, trip_id=trip_id).select_related("route").first()
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
        station = _station_of(st.stop)
        stops.append(
            {
                "sequence": st.stop_sequence,
                "stop_id": st.stop.stop_id,
                "station_id": station.stop_id,
                "name": station.name,
                "arrival": _time_dict(
                    ctx, st.arrival_secs, service_date, est.arrival, est.arrival_delay
                ),
                "departure": _time_dict(
                    ctx, st.departure_secs, service_date, est.departure, est.departure_delay
                ),
                "skipped": est.skipped,
            }
        )
    vehicle = next(iter(vehicles(ctx, trip_ids=[trip.trip_id])), None)
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
    origin = board.zone_id or (board.parent_station.zone_id if board.parent_station_id else "")
    dest = alight.zone_id or (alight.parent_station.zone_id if alight.parent_station_id else "")
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


def vehicles(ctx: Context, trip_ids=None) -> list[dict]:
    from transit.models import RealtimeKind
    from transit.realtime.overlay import is_fresh

    if not is_fresh(ctx.operator, RealtimeKind.VEHICLE_POSITIONS):
        return []
    positions = VehiclePosition.objects.filter(operator=ctx.operator)
    if trip_ids is not None:
        positions = positions.filter(trip_id__in=trip_ids)
    positions = list(positions.order_by("trip_id", "vehicle_id"))
    trips = {
        t.trip_id: t
        for t in Trip.objects.filter(
            feed=ctx.feed, trip_id__in={p.trip_id for p in positions if p.trip_id}
        ).select_related("route")
    }
    result = []
    for p in positions:
        trip = trips.get(p.trip_id)
        result.append(
            {
                "vehicle_id": p.vehicle_id or p.label,
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
            }
        )
    return result
