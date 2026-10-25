"""Lay realtime predictions over scheduled stop times.

Follows the GTFS-realtime propagation rules: a delay observed at a stop
carries forward to later stops with no update of their own, until the next
update or a NO_DATA stop. Stops before the first update get no estimate,
because the vehicle has usually passed them already.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from django.conf import settings
from django.utils import timezone

from transit.models import (
    RealtimeFetch,
    RealtimeKind,
    StopRelationship,
    TripRelationship,
    TripUpdate,
)

# Without a start_date in the feed (511 omits it), a prediction is assumed to
# be for whichever service day puts it within this window of the schedule.
MAX_PLAUSIBLE_DELAY = timedelta(hours=3)


@dataclass
class Call:
    """One scheduled stop of one trip on one service date."""

    stop_sequence: int
    stop_id: str
    arrival: datetime | None
    departure: datetime | None


@dataclass
class Estimate:
    arrival: datetime | None = None
    departure: datetime | None = None
    arrival_delay: int | None = None
    departure_delay: int | None = None
    skipped: bool = False


@dataclass
class TripRealtime:
    status: str = "scheduled"  # scheduled | live | canceled
    estimates: dict[int, Estimate] = field(default_factory=dict)  # by stop_sequence

    def at(self, stop_sequence) -> Estimate:
        return self.estimates.get(stop_sequence) or Estimate()


def is_fresh(operator, kind) -> bool:
    fetch = RealtimeFetch.objects.filter(operator=operator, kind=kind).first()
    if fetch is None or fetch.fetched_at is None:
        return False
    max_age = timedelta(seconds=settings.TRANSIT["REALTIME_MAX_AGE"])
    return timezone.now() - fetch.fetched_at <= max_age


class RealtimeIndex:
    """Trip updates for a set of trips, loaded in two queries."""

    def __init__(self, operator, trip_ids):
        self.by_trip = {}
        if not trip_ids or not is_fresh(operator, RealtimeKind.TRIP_UPDATES):
            return
        updates = TripUpdate.objects.filter(
            operator=operator, trip_id__in=set(trip_ids)
        ).prefetch_related("stop_time_updates")
        for update in updates:
            self.by_trip.setdefault(update.trip_id, []).append(update)

    def covers(self, trip_id) -> bool:
        return trip_id in self.by_trip

    def for_trip(self, trip_id, service_date: date, calls: list[Call]) -> TripRealtime:
        candidates = self.by_trip.get(trip_id, [])
        dated = [u for u in candidates if u.start_date == service_date]
        undated = [u for u in candidates if u.start_date is None]
        update = (dated or undated or [None])[0]
        if update is None:
            return TripRealtime()
        if update.schedule_relationship in (TripRelationship.CANCELED, TripRelationship.DELETED):
            return TripRealtime(status="canceled")

        result = _apply(update, calls)
        if update.start_date is None and not _plausible(result, calls):
            # Most likely the same trip_id on another service day.
            return TripRealtime()
        return result


def _apply(update, calls) -> TripRealtime:
    by_seq = {}
    by_stop = {}
    for stu in update.stop_time_updates.all():
        if stu.stop_sequence is not None:
            by_seq[stu.stop_sequence] = stu
        if stu.stop_id:
            by_stop.setdefault(stu.stop_id, stu)

    result = TripRealtime(status="live")
    carried = update.delay  # a trip-level delay applies until a stop says otherwise
    for call in calls:
        stu = by_seq.get(call.stop_sequence) or by_stop.get(call.stop_id)
        if stu is not None:
            if stu.schedule_relationship == StopRelationship.NO_DATA:
                carried = None
                continue
            if stu.schedule_relationship == StopRelationship.SKIPPED:
                result.estimates[call.stop_sequence] = Estimate(skipped=True)
                continue
            arrival_delay = _delay(stu.arrival_time, stu.arrival_delay, call.arrival)
            departure_delay = _delay(stu.departure_time, stu.departure_delay, call.departure)
            if arrival_delay is None:
                arrival_delay = departure_delay if departure_delay is not None else carried
            if departure_delay is None:
                departure_delay = arrival_delay
            carried = departure_delay
        elif carried is not None:
            arrival_delay = departure_delay = carried
        else:
            continue
        estimate = Estimate(arrival_delay=arrival_delay, departure_delay=departure_delay)
        if call.arrival and arrival_delay is not None:
            estimate.arrival = call.arrival + timedelta(seconds=arrival_delay)
        if call.departure and departure_delay is not None:
            # A train can't leave before it arrives, whatever the feed says.
            estimate.departure = call.departure + timedelta(seconds=departure_delay)
            if estimate.arrival and estimate.departure < estimate.arrival:
                estimate.departure = estimate.arrival
                estimate.departure_delay = int(
                    (estimate.departure - call.departure).total_seconds()
                )
        result.estimates[call.stop_sequence] = estimate
    return result


def _delay(predicted: datetime | None, delay: int | None, scheduled: datetime | None):
    if predicted is not None and scheduled is not None:
        return int((predicted - scheduled).total_seconds())
    return delay


def _plausible(result, calls) -> bool:
    for call in calls:
        est = result.estimates.get(call.stop_sequence)
        if est and est.departure_delay is not None:
            return abs(est.departure_delay) <= MAX_PLAUSIBLE_DELAY.total_seconds()
    return True
