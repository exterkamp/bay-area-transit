import zipfile

import pytest

from transit.gtfs.calendar import active_service_ids
from transit.gtfs.importer import GTFSValidationError, delete_feed, import_feed, prune_feeds
from transit.models import (
    FareAttribute,
    Feed,
    LocationType,
    Route,
    Service,
    Shape,
    Stop,
    StopTime,
    Trip,
)

from .conftest import MINI


def test_imports_everything(feed):
    assert feed.is_active
    assert feed.version == "v1"
    assert str(feed.start_date) == "2026-01-01"
    counts = feed.stats["counts"]
    assert counts == {
        "agencies": 1,
        "stops": 10,
        "routes": 2,
        "services": 3,
        "service_dates": 4,
        "shapes": 1,
        "trips": 6,
        "stop_times": 16,
        "fares": 3,
        "fare_rules": 4,
    }
    assert feed.operator.timezone == "America/Los_Angeles"
    assert feed.operator.name == "Test Transit"


def test_stop_hierarchy(feed):
    mid = Stop.objects.get(feed=feed, stop_id="mid")
    assert mid.location_type == LocationType.STATION
    assert {c.stop_id for c in mid.children.all()} == {"mid_nb", "mid_sb", "mid_entrance"}
    assert Stop.objects.get(feed=feed, stop_id="mid_nb").wheelchair_boarding == 0


def test_route_colors_normalized(feed):
    express = Route.objects.get(feed=feed, route_id="EXP")
    assert express.color == "e31837"
    assert express.text_color == ""  # invalid, warned and dropped
    assert any("not-a-color" in w for w in feed.stats["warnings"])


def test_shape_points_are_ordered_by_sequence(feed):
    coords = Shape.objects.get(feed=feed, shape_id="s_nb").geometry.coords
    assert [round(lat, 2) for _, lat in coords] == [37.4, 37.6, 37.8]


def test_after_midnight_times_are_seconds(feed):
    last = StopTime.objects.get(trip__trip_id="T3", stop_sequence=30)
    assert last.arrival_secs == 24 * 3600 + 30 * 60


def test_untimed_stop_is_interpolated_by_distance(feed):
    mid = StopTime.objects.get(trip__trip_id="T4", stop_sequence=2)
    # 10:00 -> 10:20 over 40 units; mid is at 10 units.
    assert mid.arrival_secs == 10 * 3600 + 5 * 60
    assert mid.timepoint is False


def test_exception_only_service(feed):
    holiday = Service.objects.get(feed=feed, service_id="HOL")
    assert holiday.start_date is None
    assert not any(getattr(holiday, day) for day in Service.WEEKDAYS)


def test_fare_currency_is_uppercased(feed):
    assert FareAttribute.objects.get(feed=feed, fare_id="F12").currency_type == "USD"


def test_unused_files_are_warned_about(feed):
    assert any(w.startswith("transfers.txt") for w in feed.stats["warnings"])


def test_reimport_of_same_archive_is_a_no_op(feed):
    again = import_feed(feed.operator, MINI)
    assert not again.created
    assert again.feed == feed
    assert Feed.objects.count() == 1


def test_zip_archives_work(operator, tmp_path):
    archive = tmp_path / "feed.zip"
    with zipfile.ZipFile(archive, "w") as z:
        for f in MINI.iterdir():
            z.write(f, f"nested/{f.name}")
    feed = import_feed(operator, archive).feed
    assert feed.stats["counts"]["trips"] == 6


def test_new_feed_replaces_active_and_old_ones_are_pruned(operator, gtfs_dir):
    first = import_feed(operator, MINI).feed
    (gtfs_dir / "feed_info.txt").write_text(
        (gtfs_dir / "feed_info.txt").read_text().replace(",v1", ",v2")
    )
    second = import_feed(operator, gtfs_dir, keep=1).feed
    assert second.is_active
    assert not Feed.objects.filter(pk=first.pk).exists()
    assert Trip.objects.count() == 6  # only the second feed's


def test_prune_never_deletes_active(feed):
    prune_feeds(feed.operator, keep=0)
    assert Feed.objects.filter(pk=feed.pk).exists()


def test_delete_feed_removes_every_row(feed):
    delete_feed(feed)
    assert not Stop.objects.exists()
    assert not StopTime.objects.exists()
    assert not Service.objects.exists()


def _broken(gtfs_dir, filename, old, new):
    path = gtfs_dir / filename
    text = path.read_text()
    assert old in text
    path.write_text(text.replace(old, new))


@pytest.mark.parametrize(
    "filename,old,new,message",
    [
        ("trips.txt", "LOC,WK,T1", "NOPE,WK,T1", "route_id 'NOPE' does not exist"),
        ("trips.txt", "LOC,WK,T1", "LOC,NOPE,T1", "service_id 'NOPE' does not exist"),
        ("stop_times.txt", "T1,08:20:00,08:20:00", "T1,07:00:00,07:00:00", "goes back in time"),
        ("stop_times.txt", "T1,08:10:00,08:11:00", "T1,08:10:00,08:09:00", "before arrival_time"),
        ("stop_times.txt", "T2,8:45:00,8:45:00", "T2,,", "must be timed"),
        ("stop_times.txt", "mid_nb,2,0", "mid,2,0", "trips can only call at stops"),
        (
            "stop_times.txt",
            "T5,12:20:00,12:20:00,north_nb,2",
            "T5,12:20:00,12:20:00,north_nb,1",
            "duplicate stop_sequence",
        ),
        (
            "stops.txt",
            "mid,Mid,37.60,-122.30,,1,,",
            "mid,Mid,37.60,-122.30,,1,north,",
            "station cannot have a parent",
        ),
        (
            "stops.txt",
            "mid_entrance,Mid Main Entrance,37.6002,-122.3002,,2,mid",
            "mid_entrance,Mid Main Entrance,37.6002,-122.3002,,2,",
            "parent_station is required",
        ),
        (
            "stops.txt",
            "north_sb,North Southbound,37.7999",
            "north_sb,North Southbound,97.7999",
            "out of range",
        ),
        ("stops.txt", "Z3,0,north,1,2", "Z3,0,north_nb,1,2", "can't contain"),
        ("calendar.txt", "20260101,20271231\nWE", "20271231,20260101\nWE", "before start_date"),
        ("calendar_dates.txt", "WK,20261126,2", "WK,20261126,3", "exception_type='3'"),
        ("routes.txt", "LOC,TT,Local,,2", "LOC,XX,Local,,2", "agency_id 'XX' does not exist"),
        ("routes.txt", "LOC,TT,Local,,2", "LOC,TT,,,2", "route_short_name or route_long_name"),
        ("routes.txt", "LOC,TT,Local,,2", "LOC,TT,Local,,99", "not a GTFS route type"),
        ("fare_rules.txt", "F13,,Z1,Z3", "F99,,Z1,Z3", "fare_id 'F99' does not exist"),
    ],
)
def test_invalid_feeds_are_rejected_whole(operator, gtfs_dir, filename, old, new, message):
    _broken(gtfs_dir, filename, old, new)
    with pytest.raises(GTFSValidationError) as exc:
        import_feed(operator, gtfs_dir)
    assert message in str(exc.value)
    assert not Feed.objects.exists()
    assert not Stop.objects.exists()


def test_missing_required_file(operator, gtfs_dir):
    (gtfs_dir / "trips.txt").unlink()
    with pytest.raises(GTFSValidationError, match="trips.txt: required file is missing"):
        import_feed(operator, gtfs_dir)


def test_missing_required_column(operator, gtfs_dir):
    _broken(gtfs_dir, "routes.txt", "route_type", "kind")
    with pytest.raises(GTFSValidationError, match="missing required column"):
        import_feed(operator, gtfs_dir)


def test_all_problems_reported_at_once(operator, gtfs_dir):
    _broken(gtfs_dir, "trips.txt", "LOC,WK,T1", "NOPE,WK,T1")
    _broken(gtfs_dir, "trips.txt", "EXP,WK,T2", "NOPE2,WK,T2")
    with pytest.raises(GTFSValidationError) as exc:
        import_feed(operator, gtfs_dir)
    assert len(exc.value.errors) == 2


class TestCalendar:
    def ids(self, feed, day):
        return set(
            Service.objects.filter(pk__in=active_service_ids(feed, day)).values_list(
                "service_id", flat=True
            )
        )

    def test_weekday(self, feed):
        from datetime import date

        assert self.ids(feed, date(2026, 10, 28)) == {"WK"}

    def test_weekend(self, feed):
        from datetime import date

        assert self.ids(feed, date(2026, 10, 24)) == {"WE"}

    def test_thanksgiving_runs_weekend_service(self, feed):
        from datetime import date

        assert self.ids(feed, date(2026, 11, 26)) == {"WE"}

    def test_christmas_runs_only_the_holiday_service(self, feed):
        from datetime import date

        assert self.ids(feed, date(2026, 12, 25)) == {"HOL"}

    def test_outside_the_calendar(self, feed):
        from datetime import date

        assert self.ids(feed, date(2028, 1, 5)) == set()
