from datetime import date
from zoneinfo import ZoneInfo

import pytest

from transit.gtfs.times import (
    format_gtfs_time,
    parse_gtfs_date,
    parse_gtfs_time,
    secs_since_service_start,
    service_day_start,
    to_datetime,
)

TZ = ZoneInfo("America/Los_Angeles")


@pytest.mark.parametrize(
    "text,secs",
    [("08:00:00", 28800), ("8:00:00", 28800), (" 25:10:00 ", 90600), ("0:00:00", 0), ("", None)],
)
def test_parse_gtfs_time(text, secs):
    assert parse_gtfs_time(text) == secs


@pytest.mark.parametrize("text", ["8:00", "08:60:00", "ab:cd:ef", "-1:00:00"])
def test_parse_gtfs_time_rejects(text):
    with pytest.raises(ValueError):
        parse_gtfs_time(text)


def test_format_round_trips():
    assert format_gtfs_time(90600) == "25:10:00"


def test_parse_gtfs_date():
    assert parse_gtfs_date("20261126") == date(2026, 11, 26)
    with pytest.raises(ValueError):
        parse_gtfs_date("2026-11-26")


def test_service_day_starts_at_midnight_normally():
    assert service_day_start(date(2026, 10, 28), TZ).astimezone(TZ).hour == 0


def test_times_keep_wall_clock_across_dst_end():
    # 2026-11-01 is the US fall-back day: "noon minus 12h" is 01:00 PDT, and
    # that is what makes 08:00:00 come out at 08:00 on the clock.
    assert service_day_start(date(2026, 11, 1), TZ).astimezone(TZ).hour == 1
    moment = to_datetime(date(2026, 11, 1), 8 * 3600, TZ).astimezone(TZ)
    assert (moment.hour, moment.minute) == (8, 0)
    assert moment.utcoffset().total_seconds() == -8 * 3600


def test_times_keep_wall_clock_across_dst_start():
    # Spring forward: noon minus 12h is 23:00 PST the evening before.
    assert service_day_start(date(2026, 3, 8), TZ).astimezone(TZ).hour == 23
    moment = to_datetime(date(2026, 3, 8), 8 * 3600, TZ).astimezone(TZ)
    assert (moment.hour, moment.minute) == (8, 0)
    assert moment.utcoffset().total_seconds() == -7 * 3600


def test_after_midnight_lands_on_next_day():
    moment = to_datetime(date(2026, 10, 28), parse_gtfs_time("24:10:00"), TZ).astimezone(TZ)
    assert (moment.day, moment.hour, moment.minute) == (29, 0, 10)


def test_secs_since_service_start_inverts_to_datetime():
    moment = to_datetime(date(2026, 10, 28), 30000, TZ)
    assert secs_since_service_start(moment, date(2026, 10, 28), TZ) == 30000
