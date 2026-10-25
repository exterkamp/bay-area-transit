"""Poll GTFS-realtime feeds and store each as a fresh snapshot."""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from django.contrib.gis.geos import Point
from django.db import transaction
from django.utils import timezone
from google.protobuf.message import DecodeError
from google.transit import gtfs_realtime_pb2

from transit.client import Client511, Client511Error
from transit.gtfs.times import parse_gtfs_date
from transit.models import (
    Agency,
    Alert,
    LocationType,
    Operator,
    RealtimeFetch,
    RealtimeKind,
    Route,
    Stop,
    StopRelationship,
    StopTime,
    StopTimeUpdate,
    Trip,
    TripRelationship,
    TripUpdate,
    VehiclePosition,
    VehicleStatus,
)

logger = logging.getLogger(__name__)

FeedMessage = gtfs_realtime_pb2.FeedMessage
_ALERT = gtfs_realtime_pb2.Alert


def _epoch(value):
    return datetime.fromtimestamp(value, tz=UTC) if value else None


def _date(value):
    try:
        return parse_gtfs_date(value) if value else None
    except ValueError:
        return None


def _has(message, name):
    try:
        return message.HasField(name)
    except ValueError:
        return False


def _translated(text):
    """Pick the English (or untagged, or first) translation of a TranslatedString."""
    if not text.translation:
        return ""
    for t in text.translation:
        if t.language in ("en", "en-US", ""):
            return t.text
    return text.translation[0].text


@dataclass(frozen=True)
class Scope:
    """The ids a filtered static feed kept. Realtime about anything else is dropped.

    511's regional feed covers ~41 agencies in one realtime request, and we
    import a few of them. Without a filter there is no scope and everything
    is stored, including trips the static feed lacks, such as added trips.
    """

    agencies: frozenset[str]
    routes: frozenset[str]
    stops: frozenset[str]
    trips: frozenset[str]

    @classmethod
    def for_operator(cls, operator) -> "Scope | None":
        feed = operator.active_feed
        if feed is None or "filter" not in feed.stats:
            return None

        def ids(model, column):
            return frozenset(model.objects.filter(feed=feed).values_list(column, flat=True))

        return cls(
            agencies=ids(Agency, "agency_id"),
            routes=ids(Route, "route_id"),
            stops=ids(Stop, "stop_id"),
            trips=ids(Trip, "trip_id"),
        )

    def informs(self, entity) -> bool:
        """Whether an alert's EntitySelector is about something we kept.

        A selector's fields narrow each other, so every one that is set must match.
        """
        trip_id = entity.trip.trip_id if _has(entity, "trip") else ""
        checks = [
            (entity.agency_id, self.agencies),
            (entity.route_id, self.routes),
            (entity.stop_id, self.stops),
            (trip_id, self.trips),
        ]
        given = [(value, kept) for value, kept in checks if value]
        return bool(given) and all(value in kept for value, kept in given)


def poll(operator: Operator, kind: str, client: Client511 | None = None) -> int:
    """Fetch one realtime feed and replace its snapshot. Returns the entity count.

    Failures are recorded on the RealtimeFetch row and re-raised; the previous
    snapshot is left in place, and the API's staleness check retires it.
    """
    attempted = timezone.now()
    try:
        client = client or Client511()
        message = FeedMessage()
        message.ParseFromString(client.realtime(kind, operator.code))
    except (Client511Error, DecodeError) as exc:
        RealtimeFetch.objects.update_or_create(
            operator=operator, kind=kind, defaults={"attempted_at": attempted, "error": str(exc)}
        )
        raise
    return store(operator, kind, message, attempted)


def store(operator, kind, message, attempted=None) -> int:
    """Replace the snapshot for (operator, kind) with ``message``."""
    attempted = attempted or timezone.now()
    if kind not in STORERS:
        raise ValueError(f"unknown realtime kind {kind!r}")
    scope = Scope.for_operator(operator)
    with transaction.atomic():
        count = STORERS[kind](operator, message, scope)
        RealtimeFetch.objects.update_or_create(
            operator=operator,
            kind=kind,
            defaults={
                "attempted_at": attempted,
                "fetched_at": attempted,
                "feed_timestamp": _epoch(message.header.timestamp),
                "entity_count": count,
                "error": "",
            },
        )
    logger.info("%s %s: %d of %d entities kept", operator.code, kind, count, len(message.entity))
    return count


def _store_trip_updates(operator, message, scope):
    # Delete the children directly: a cascade from TripUpdate would make
    # Django load every StopTimeUpdate first.
    StopTimeUpdate.objects.filter(trip_update__operator=operator).delete()
    TripUpdate.objects.filter(operator=operator).delete()
    updates = []
    stop_updates = []  # one list per entry in updates
    for entity in message.entity:
        if entity.is_deleted or not _has(entity, "trip_update"):
            continue
        tu = entity.trip_update
        if not tu.trip.trip_id:
            # Without a trip_id there is nothing in the static feed to attach to.
            continue
        if scope and tu.trip.trip_id not in scope.trips:
            continue
        relationship = tu.trip.schedule_relationship
        if relationship not in TripRelationship.values:
            relationship = TripRelationship.SCHEDULED
        updates.append(
            TripUpdate(
                operator=operator,
                trip_id=tu.trip.trip_id,
                start_date=_date(tu.trip.start_date),
                schedule_relationship=relationship,
                vehicle_id=tu.vehicle.id if _has(tu, "vehicle") else "",
                delay=tu.delay if _has(tu, "delay") else None,
                timestamp=_epoch(tu.timestamp),
            )
        )
        stop_updates.append(_stop_time_updates(tu))
    # Postgres returns the new primary keys, so the children can point at them.
    TripUpdate.objects.bulk_create(updates, batch_size=2000)
    for update, children in zip(updates, stop_updates, strict=True):
        for child in children:
            child.trip_update = update
    StopTimeUpdate.objects.bulk_create(
        [child for children in stop_updates for child in children], batch_size=5000
    )
    return len(updates)


def _stop_time_updates(tu):
    result = []
    for stu in tu.stop_time_update:
        has_seq = _has(stu, "stop_sequence")
        if not has_seq and not stu.stop_id:
            continue
        arrival = stu.arrival if _has(stu, "arrival") else None
        departure = stu.departure if _has(stu, "departure") else None
        result.append(
            StopTimeUpdate(
                stop_sequence=stu.stop_sequence if has_seq else None,
                stop_id=stu.stop_id,
                arrival_delay=arrival.delay if arrival and _has(arrival, "delay") else None,
                arrival_time=_epoch(arrival.time) if arrival and arrival.time else None,
                departure_delay=departure.delay if departure and _has(departure, "delay") else None,
                departure_time=_epoch(departure.time) if departure and departure.time else None,
                schedule_relationship=stu.schedule_relationship
                if stu.schedule_relationship in StopRelationship.values
                else StopRelationship.SCHEDULED,
            )
        )
    return result


def _store_vehicles(operator, message, scope):
    VehiclePosition.objects.filter(operator=operator).delete()
    vehicles = []
    for entity in message.entity:
        if entity.is_deleted or not _has(entity, "vehicle"):
            continue
        v = entity.vehicle
        if not _has(v, "position"):
            continue
        trip_id = v.trip.trip_id if _has(v, "trip") else ""
        if scope and trip_id not in scope.trips:
            # Includes vehicles with no trip: nothing says which agency runs them.
            continue
        lat, lon = v.position.latitude, v.position.longitude
        if not (-90 <= lat <= 90 and -180 <= lon <= 180) or (lat == 0 and lon == 0):
            continue
        bearing = v.position.bearing if _has(v.position, "bearing") else None
        if bearing is not None and not 0 <= bearing < 360:
            bearing %= 360
        vehicles.append(
            VehiclePosition(
                operator=operator,
                vehicle_id=v.vehicle.id if _has(v, "vehicle") else "",
                label=v.vehicle.label if _has(v, "vehicle") else "",
                trip_id=trip_id,
                start_date=_date(v.trip.start_date) if _has(v, "trip") else None,
                point=Point(lon, lat, srid=4326),
                bearing=bearing,
                speed=v.position.speed if _has(v.position, "speed") else None,
                current_status=v.current_status
                if _has(v, "current_status") and v.current_status in VehicleStatus.values
                else None,
                stop_id=v.stop_id,
                current_stop_sequence=v.current_stop_sequence
                if _has(v, "current_stop_sequence")
                else None,
                timestamp=_epoch(v.timestamp),
            )
        )
    VehiclePosition.objects.bulk_create(vehicles)
    return len(vehicles)


def _store_alerts(operator, message, scope):
    Alert.objects.filter(operator=operator).delete()
    alerts = {}
    named = {}
    for entity in message.entity:
        if entity.is_deleted or not _has(entity, "alert"):
            continue
        a = entity.alert
        informed = a.informed_entity
        if scope and not any(scope.informs(e) for e in informed):
            continue
        named[entity.id] = {e.agency_id for e in informed if e.agency_id}
        alerts[entity.id] = Alert(
            operator=operator,
            alert_id=entity.id,
            header=_translated(a.header_text),
            description=_translated(a.description_text),
            url=_translated(a.url),
            cause=_ALERT.Cause.Name(a.cause).lower() if _has(a, "cause") else "",
            effect=_ALERT.Effect.Name(a.effect).lower() if _has(a, "effect") else "",
            active_periods=[[p.start or None, p.end or None] for p in a.active_period],
            route_ids=sorted({e.route_id for e in informed if e.route_id}),
            stop_ids=sorted({e.stop_id for e in informed if e.stop_id}),
            trip_ids=sorted(
                {e.trip.trip_id for e in informed if _has(e, "trip") and e.trip.trip_id}
            ),
        )
    if operator.active_feed:
        _set_agencies(operator.active_feed, alerts, named)
    Alert.objects.bulk_create(alerts.values())
    return len(alerts)


def _set_agencies(feed, alerts, named):
    """Fill each alert's agencies: named, or behind its routes and stops.

    Done once per poll rather than per request: alerts can list dozens of
    stops, and finding the routes that call at them reads stop times.
    """
    route_ids = {r for a in alerts.values() for r in a.route_ids}
    stop_ids = {s for a in alerts.values() for s in a.stop_ids}
    of_route = dict(
        Route.objects.filter(feed=feed, route_id__in=route_ids).values_list(
            "route_id", "agency__agency_id"
        )
    )
    # A platform counts the routes that call at it, not its whole station: a
    # Muni platform at Embarcadero isn't news for BART. A station id named
    # directly counts every route at the station.
    stops = dict(Stop.objects.filter(feed=feed, stop_id__in=stop_ids).values_list("pk", "stop_id"))
    of_stop = {}
    for stop_pk, agency_id in (
        StopTime.objects.filter(stop_id__in=stops)
        .values_list("stop_id", "trip__route__agency__agency_id")
        .distinct()
    ):
        of_stop.setdefault(stops[stop_pk], set()).add(agency_id)
    for stop_id, agency_id in Stop.objects.filter(
        feed=feed,
        stop_id__in=stop_ids - of_stop.keys(),
        location_type=LocationType.STATION,
    ).values_list("stop_id", "place__routes__agency__agency_id"):
        if agency_id:
            of_stop.setdefault(stop_id, set()).add(agency_id)
    known = set(Agency.objects.filter(feed=feed).values_list("agency_id", flat=True))
    for key, alert in alerts.items():
        found = named[key] & known
        found |= {of_route[r] for r in alert.route_ids if r in of_route}
        for s in alert.stop_ids:
            found |= of_stop.get(s, set())
        alert.agencies = sorted(found)


STORERS = {
    RealtimeKind.TRIP_UPDATES: _store_trip_updates,
    RealtimeKind.VEHICLE_POSITIONS: _store_vehicles,
    RealtimeKind.ALERTS: _store_alerts,
}
