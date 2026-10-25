"""Where a vehicle should be, from its trip's predicted stop times.

For agencies that publish predictions but no GPS (BART), a vehicle's place
is inferred: standing at a platform between its predicted arrival and
departure there, else between the last stop it left and the next one,
moved along the route's shape in proportion to the time elapsed. Pure
functions over plain values, so they test without a database.
"""

import math
from dataclasses import dataclass
from datetime import datetime

from django.contrib.gis.geos import LineString, Point

from transit.models import VehicleStatus


@dataclass(frozen=True)
class TimedStop:
    """One call of a trip, with the best known times: predicted, else scheduled."""

    stop_sequence: int
    stop_id: str
    point: Point
    arrival: datetime | None
    departure: datetime | None


@dataclass(frozen=True)
class Placement:
    point: Point
    bearing: float | None
    status: int
    stop_id: str


def place(
    stops: list[TimedStop], now: datetime, shape: LineString | None = None
) -> Placement | None:
    """Where the trip is at ``now``, or None before it leaves or after it ends."""
    stops = [s for s in stops if s.arrival or s.departure]
    if len(stops) < 2:
        return None
    first, last = stops[0], stops[-1]
    if now < (first.departure or first.arrival) or now > (last.arrival or last.departure):
        return None

    for prev, nxt in zip(stops, stops[1:], strict=False):
        arrive = prev.arrival or prev.departure
        leave = prev.departure or prev.arrival
        if arrive <= now <= leave:
            return Placement(
                prev.point,
                _bearing_at(shape, prev.point, nxt.point),
                VehicleStatus.STOPPED_AT,
                prev.stop_id,
            )
        next_arrival = nxt.arrival or nxt.departure
        if leave < now < next_arrival:
            fraction = (now - leave) / (next_arrival - leave)
            point, bearing = _between(shape, prev.point, nxt.point, fraction)
            return Placement(point, bearing, VehicleStatus.IN_TRANSIT_TO, nxt.stop_id)
    # At the last stop, on its arrival time to the second.
    return Placement(last.point, None, VehicleStatus.STOPPED_AT, last.stop_id)


def _between(shape, a: Point, b: Point, fraction: float):
    """A point ``fraction`` of the way from a to b, along the shape if it runs that way."""
    if shape is not None:
        start, end = shape.project(a), shape.project(b)
        if end > start:
            here = shape.interpolate(start + (end - start) * fraction)
            ahead = shape.interpolate(min(end, start + (end - start) * fraction + _STEP))
            behind = shape.interpolate(max(start, start + (end - start) * fraction - _STEP))
            return Point(here.x, here.y, srid=4326), _heading(behind, ahead)
    # No shape, or it doesn't run from a to b (a loop doubling back): straight line.
    x = a.x + (b.x - a.x) * fraction
    y = a.y + (b.y - a.y) * fraction
    return Point(x, y, srid=4326), _heading(a, b)


def _bearing_at(shape, here: Point, toward: Point):
    if shape is None:
        return _heading(here, toward)
    d = shape.project(here)
    return _heading(shape.interpolate(max(0, d - _STEP)), shape.interpolate(d + _STEP))


# About 50 m in degrees: enough to read a direction off a curvy shape.
_STEP = 0.0005


def _heading(a: Point, b: Point) -> float | None:
    """Compass bearing from a to b in degrees, None if they coincide."""
    dx = (b.x - a.x) * math.cos(math.radians((a.y + b.y) / 2))
    dy = b.y - a.y
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return None
    return round(math.degrees(math.atan2(dx, dy)), 1) % 360
