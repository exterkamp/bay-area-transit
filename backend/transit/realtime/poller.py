"""Poll GTFS-realtime feeds and store each as a fresh snapshot."""

import logging
from datetime import UTC, datetime

from django.contrib.gis.geos import Point
from django.db import transaction
from django.utils import timezone
from google.protobuf.message import DecodeError
from google.transit import gtfs_realtime_pb2

from transit.client import Client511, Client511Error
from transit.gtfs.times import parse_gtfs_date
from transit.models import (
    Alert,
    Operator,
    RealtimeFetch,
    RealtimeKind,
    StopRelationship,
    StopTimeUpdate,
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
    with transaction.atomic():
        if kind == RealtimeKind.TRIP_UPDATES:
            count = _store_trip_updates(operator, message)
        elif kind == RealtimeKind.VEHICLE_POSITIONS:
            count = _store_vehicles(operator, message)
        elif kind == RealtimeKind.ALERTS:
            count = _store_alerts(operator, message)
        else:
            raise ValueError(f"unknown realtime kind {kind!r}")
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
    logger.info("%s %s: %d entities", operator.code, kind, count)
    return count


def _store_trip_updates(operator, message):
    TripUpdate.objects.filter(operator=operator).delete()
    stop_updates = []
    count = 0
    for entity in message.entity:
        if entity.is_deleted or not _has(entity, "trip_update"):
            continue
        tu = entity.trip_update
        if not tu.trip.trip_id:
            # Without a trip_id there is nothing in the static feed to attach to.
            continue
        relationship = tu.trip.schedule_relationship
        if relationship not in TripRelationship.values:
            relationship = TripRelationship.SCHEDULED
        trip_update = TripUpdate.objects.create(
            operator=operator,
            trip_id=tu.trip.trip_id,
            start_date=_date(tu.trip.start_date),
            schedule_relationship=relationship,
            vehicle_id=tu.vehicle.id if _has(tu, "vehicle") else "",
            delay=tu.delay if _has(tu, "delay") else None,
            timestamp=_epoch(tu.timestamp),
        )
        count += 1
        for stu in tu.stop_time_update:
            has_seq = _has(stu, "stop_sequence")
            if not has_seq and not stu.stop_id:
                continue
            arrival = stu.arrival if _has(stu, "arrival") else None
            departure = stu.departure if _has(stu, "departure") else None
            stop_updates.append(
                StopTimeUpdate(
                    trip_update=trip_update,
                    stop_sequence=stu.stop_sequence if has_seq else None,
                    stop_id=stu.stop_id,
                    arrival_delay=arrival.delay if arrival and _has(arrival, "delay") else None,
                    arrival_time=_epoch(arrival.time) if arrival and arrival.time else None,
                    departure_delay=departure.delay
                    if departure and _has(departure, "delay")
                    else None,
                    departure_time=_epoch(departure.time) if departure and departure.time else None,
                    schedule_relationship=stu.schedule_relationship
                    if stu.schedule_relationship in StopRelationship.values
                    else StopRelationship.SCHEDULED,
                )
            )
    StopTimeUpdate.objects.bulk_create(stop_updates, batch_size=2000)
    return count


def _store_vehicles(operator, message):
    VehiclePosition.objects.filter(operator=operator).delete()
    vehicles = []
    for entity in message.entity:
        if entity.is_deleted or not _has(entity, "vehicle"):
            continue
        v = entity.vehicle
        if not _has(v, "position"):
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
                trip_id=v.trip.trip_id if _has(v, "trip") else "",
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


def _store_alerts(operator, message):
    Alert.objects.filter(operator=operator).delete()
    alerts = {}
    for entity in message.entity:
        if entity.is_deleted or not _has(entity, "alert"):
            continue
        a = entity.alert
        informed = a.informed_entity
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
    Alert.objects.bulk_create(alerts.values())
    return len(alerts)
