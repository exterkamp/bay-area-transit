"""GTFS time arithmetic.

A GTFS stop time is an offset from the start of a *service day*, which the
spec defines as "noon minus 12 hours" in the agency's timezone. That is
midnight on every day except DST transitions, where it is 23:00 or 01:00 -
which is exactly what keeps a 08:00:00 train at 08:00 local on those days.
Offsets can exceed 24h for trips that run past midnight.
"""

import re
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

_TIME = re.compile(r"^\s*(\d{1,3}):([0-5]\d):([0-5]\d)\s*$")


def parse_gtfs_time(value: str) -> int | None:
    """'25:10:00' -> 90600. Blank -> None. Anything else -> ValueError."""
    if value is None or not value.strip():
        return None
    match = _TIME.match(value)
    if not match:
        raise ValueError(f"not a GTFS time (H:MM:SS): {value!r}")
    hours, minutes, seconds = (int(part) for part in match.groups())
    return hours * 3600 + minutes * 60 + seconds


def format_gtfs_time(secs: int) -> str:
    return f"{secs // 3600:02d}:{secs % 3600 // 60:02d}:{secs % 60:02d}"


def parse_gtfs_date(value: str) -> date:
    """'20260131' -> date(2026, 1, 31)."""
    value = value.strip()
    if len(value) != 8 or not value.isdigit():
        raise ValueError(f"not a GTFS date (YYYYMMDD): {value!r}")
    return date(int(value[:4]), int(value[4:6]), int(value[6:]))


def service_day_start(service_date: date, tz: ZoneInfo) -> datetime:
    """The instant GTFS times on ``service_date`` count from, in UTC.

    The arithmetic happens in UTC on purpose: adding a timedelta to a zoneinfo
    datetime moves the wall clock, not elapsed time, which gets DST days wrong.
    """
    noon = datetime.combine(service_date, time(12), tzinfo=tz)
    return noon.astimezone(UTC) - timedelta(hours=12)


def to_datetime(service_date: date, secs: int, tz: ZoneInfo) -> datetime:
    """A stop time on a service date, as an aware UTC datetime.

    Everything internal stays in UTC; convert to the agency's zone only for
    display. Comparing or offsetting two datetimes that share a zoneinfo uses
    wall-clock time, which is wrong for the repeated hour when DST ends.
    """
    return service_day_start(service_date, tz) + timedelta(seconds=secs)


def secs_since_service_start(moment: datetime, service_date: date, tz: ZoneInfo) -> int:
    """How far ``moment`` is into ``service_date``'s GTFS clock (may be negative)."""
    return int((moment - service_day_start(service_date, tz)).total_seconds())
