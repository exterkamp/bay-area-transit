import shutil

import pytest

from transit.gtfs.importer import FeedFilter, GTFSValidationError, import_feed
from transit.models import Agency, Feed, Route, Service, ServiceDate, Shape, Stop, StopTime, Trip

from .conftest import REGIONAL


def ids(model, field, feed):
    return set(model.objects.filter(feed=feed).values_list(field, flat=True))


class TestFeedFilter:
    def test_parse_and_spec(self):
        only = FeedFilter.parse(" SF:0, BA ,SM,CT:2+0 ")
        assert only.spec == "BA,CT:0+2,SF:0,SM"
        assert only.keeps_route("SF", 0)
        assert not only.keeps_route("SF", 3)
        assert only.keeps_route("BA", 3)
        assert not only.keeps_agency("AC")

    def test_blank_means_no_filter(self):
        assert FeedFilter.parse("") is None
        assert FeedFilter.parse(None) is None

    def test_bad_types(self):
        with pytest.raises(ValueError):
            FeedFilter.parse("SF:rail")


def test_rail_only_from_one_agency(operator):
    feed = import_feed(operator, REGIONAL, only=FeedFilter.parse("RA:0")).feed
    assert ids(Agency, "agency_id", feed) == {"RA"}
    assert ids(Route, "route_id", feed) == {"RA:L"}  # not the cable car
    assert ids(Trip, "trip_id", feed) == {"RA:1"}
    # Only stops the kept trip calls at, plus their stations.
    assert ids(Stop, "stop_id", feed) == {"hub", "hub_rail", "far", "far_rail"}
    assert ids(Service, "service_id", feed) == {"RA:WK"}
    assert ServiceDate.objects.filter(feed=feed).count() == 1
    assert ids(Shape, "shape_id", feed) == {"RA:s1"}
    assert StopTime.objects.filter(feed=feed).count() == 2
    assert feed.stats["filter"] == "RA:0"


def test_validity_comes_from_the_calendar_without_feed_info(operator):
    feed = import_feed(operator, REGIONAL, only=FeedFilter.parse("RA")).feed
    assert (str(feed.start_date), str(feed.end_date)) == ("2026-01-01", "2027-12-31")


def test_multi_agency_operator_is_not_named_after_one_agency(operator):
    import_feed(operator, REGIONAL, only=FeedFilter.parse("RA,BU"))
    operator.refresh_from_db()
    assert operator.name == "TT"


def test_two_agencies_share_a_station(operator):
    feed = import_feed(operator, REGIONAL, only=FeedFilter.parse("RA,BU")).feed
    hub = Stop.objects.get(feed=feed, stop_id="hub")
    assert {c.stop_id for c in hub.children.all()} == {"hub_rail", "hub_bay"}
    assert ids(Trip, "trip_id", feed) == {"RA:1", "RA:2", "BU:1"}
    assert "x_stop" not in ids(Stop, "stop_id", feed)
    assert "unused" not in ids(Stop, "stop_id", feed)


def test_no_filter_keeps_everything(operator):
    feed = import_feed(operator, REGIONAL).feed
    assert len(ids(Trip, "trip_id", feed)) == 4
    assert "unused" in ids(Stop, "stop_id", feed)


def test_filter_naming_a_missing_agency_is_an_error(operator):
    with pytest.raises(GTFSValidationError, match="names agency 'ZZ'"):
        import_feed(operator, REGIONAL, only=FeedFilter.parse("RA,ZZ"))


def test_dangling_references_still_caught_when_filtering(operator, tmp_path):
    import shutil

    target = tmp_path / "regional"
    shutil.copytree(REGIONAL, target)
    with open(target / "stop_times.txt", "a") as f:
        f.write("RA:404,11:00:00,11:00:00,hub_rail,1\n")
    with pytest.raises(GTFSValidationError, match="trip_id 'RA:404' does not exist"):
        import_feed(operator, target, only=FeedFilter.parse("RA"))


def test_same_archive_different_filter_is_a_new_feed(operator):
    first = import_feed(operator, REGIONAL, only=FeedFilter.parse("RA"))
    again = import_feed(operator, REGIONAL, only=FeedFilter.parse("RA"))
    other = import_feed(operator, REGIONAL, only=FeedFilter.parse("RA,BU"))
    assert first.created and not again.created and other.created
    assert Feed.objects.count() == 2


def test_validity_is_while_every_kept_agency_is_valid(operator):
    feed = import_feed(operator, REGIONAL, only=FeedFilter.parse("RA,BU")).feed
    # RA runs 2026-2027, BU only March to November 2026.
    assert (str(feed.start_date), str(feed.end_date)) == ("2026-03-01", "2026-11-30")
    bu = Agency.objects.get(feed=feed, agency_id="BU")
    assert (bu.feed_version, str(bu.start_date), str(bu.end_date)) == (
        "20260301",
        "2026-03-01",
        "2026-11-30",
    )


def test_without_overlap_the_feed_ends_when_the_first_agency_does(operator, tmp_path):
    target = tmp_path / "regional"
    shutil.copytree(REGIONAL, target)
    versions = target / "mtc_feed_versions.txt"
    versions.write_text(
        versions.read_text().replace(
            "BU,20260301,bbbb,20260301,20261130", "BU,1,b,20280101,20281231"
        )
    )
    feed = import_feed(operator, target, only=FeedFilter.parse("RA,BU")).feed
    assert (str(feed.start_date), str(feed.end_date)) == ("2026-01-01", "2027-12-31")


def test_without_versions_validity_comes_from_the_calendar(operator, tmp_path):
    target = tmp_path / "regional"
    shutil.copytree(REGIONAL, target)
    (target / "mtc_feed_versions.txt").unlink()
    feed = import_feed(operator, target, only=FeedFilter.parse("RA,BU")).feed
    # The union of RA's and BU's calendars.
    assert (str(feed.start_date), str(feed.end_date)) == ("2026-01-01", "2027-12-31")
