"""Import a static GTFS archive as a new Feed.

The whole import runs in one transaction: a feed either lands complete and
valid, or not at all. Structural problems (missing required fields, dangling
references, times running backwards) are errors that abort the import with
every problem listed by file and line. Cosmetic ones (a malformed route
color, a file this app doesn't use) are warnings recorded on the feed.

Archives are identified by hash, so re-importing an unchanged download is a
no-op.
"""

import csv
import hashlib
import io
import logging
import zipfile
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.contrib.gis.geos import LineString, Point
from django.db import connection, transaction

from transit.models import (
    Agency,
    ExceptionType,
    FareAttribute,
    FareRule,
    Feed,
    LocationType,
    Operator,
    Route,
    Service,
    ServiceDate,
    Shape,
    Stop,
    StopTime,
    Trip,
)

from .times import parse_gtfs_date, parse_gtfs_time

logger = logging.getLogger(__name__)

BATCH = 5000
MAX_ERRORS = 50

# Files the importer reads. Anything else in the archive is noted and skipped.
SUPPORTED = {
    "agency.txt",
    "stops.txt",
    "routes.txt",
    "trips.txt",
    "stop_times.txt",
    "calendar.txt",
    "calendar_dates.txt",
    "shapes.txt",
    "feed_info.txt",
    "fare_attributes.txt",
    "fare_rules.txt",
}


class GTFSValidationError(Exception):
    def __init__(self, errors):
        self.errors = errors
        shown = "\n".join(f"  {e}" for e in errors[:MAX_ERRORS])
        more = f"\n  ... and {len(errors) - MAX_ERRORS} more" if len(errors) > MAX_ERRORS else ""
        super().__init__(f"GTFS feed is invalid ({len(errors)} problems):\n{shown}{more}")


@dataclass
class Problems:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def error(self, where, message):
        self.errors.append(f"{where}: {message}")

    def warn(self, where, message):
        self.warnings.append(f"{where}: {message}")

    def check(self):
        """Stop here if anything so far is fatal; later files would only pile on."""
        if self.errors:
            raise GTFSValidationError(self.errors)


@dataclass
class ImportResult:
    feed: Feed
    created: bool


class Archive:
    """A GTFS archive as a zip (path or bytes) or an extracted directory."""

    def __init__(self, source):
        if isinstance(source, bytes):
            self._zip = zipfile.ZipFile(io.BytesIO(source))
            self.sha256 = hashlib.sha256(source).hexdigest()
            self._dir = None
        else:
            path = Path(source)
            if path.is_dir():
                self._zip = None
                self._dir = path
                digest = hashlib.sha256()
                for child in sorted(path.glob("*.txt")):
                    digest.update(child.name.encode())
                    digest.update(child.read_bytes())
                self.sha256 = digest.hexdigest()
            else:
                data = path.read_bytes()
                self._zip = zipfile.ZipFile(io.BytesIO(data))
                self.sha256 = hashlib.sha256(data).hexdigest()
                self._dir = None
        self.names = self._list()

    def _list(self):
        if self._zip is not None:
            # Some publishers nest everything one folder deep.
            return {Path(n).name: n for n in self._zip.namelist() if n.endswith(".txt")}
        return {p.name: p for p in self._dir.glob("*.txt")}

    def has(self, name):
        return name in self.names

    def rows(self, name, problems, required=()):
        """Yield (location, row) for each data row, with keys and values stripped."""
        if not self.has(name):
            return
        if self._zip is not None:
            raw = self._zip.open(self.names[name])
        else:
            raw = open(self.names[name], "rb")  # noqa: SIM115 - closed below
        with io.TextIOWrapper(raw, encoding="utf-8-sig", newline="") as text:
            reader = csv.reader(text)
            header = next(reader, None)
            if header is None:
                return
            header = [h.strip() for h in header]
            missing = [col for col in required if col not in header]
            if missing:
                problems.error(name, f"missing required column(s) {', '.join(missing)}")
                return
            width = len(header)
            for values in reader:
                where = f"{name}:{reader.line_num}"
                if not any(v.strip() for v in values):
                    continue
                if len(values) > width:
                    problems.error(where, f"{len(values)} fields but header has {width}")
                    continue
                values = [v.strip() for v in values] + [""] * (width - len(values))
                yield where, dict(zip(header, values, strict=True))


# --- field parsers ---------------------------------------------------------------
# Each takes the problem list so a bad value is reported where it was found
# and parsing carries on, collecting every problem in one pass.


def need(row, col, where, problems):
    value = row.get(col, "")
    if not value:
        problems.error(where, f"{col} is required")
    return value


def enum(row, col, allowed, default, where, problems):
    value = row.get(col, "")
    if not value:
        return default
    try:
        number = int(value)
    except ValueError:
        number = None
    if number not in allowed:
        problems.error(where, f"{col}={value!r} is not one of {sorted(allowed)}")
        return default
    return number


def integer(row, col, where, problems, minimum=0):
    value = row.get(col, "")
    if not value:
        return None
    try:
        number = int(value)
    except ValueError:
        problems.error(where, f"{col}={value!r} is not an integer")
        return None
    if number < minimum:
        problems.error(where, f"{col}={number} is below {minimum}")
        return None
    return number


def decimal(row, col, where, problems):
    value = row.get(col, "")
    try:
        return float(value) if value else None
    except ValueError:
        problems.error(where, f"{col}={value!r} is not a number")
        return None


def gtfs_date(row, col, where, problems):
    value = row.get(col, "")
    if not value:
        return None
    try:
        return parse_gtfs_date(value)
    except ValueError as exc:
        problems.error(where, str(exc))
        return None


def gtfs_time(row, col, where, problems):
    try:
        return parse_gtfs_time(row.get(col, ""))
    except ValueError as exc:
        problems.error(where, f"{col}: {exc}")
        return None


def color(row, col, where, problems):
    value = row.get(col, "").lstrip("#").lower()
    if value and (len(value) != 6 or any(c not in "0123456789abcdef" for c in value)):
        problems.warn(where, f"{col}={row[col]!r} is not a hex color; ignored")
        return ""
    return value


# --- the import ------------------------------------------------------------------


def import_feed(operator: Operator, source, *, activate=True, keep=None) -> ImportResult:
    archive = Archive(source)
    existing = Feed.objects.filter(operator=operator, sha256=archive.sha256).first()
    if existing:
        logger.info("%s feed %s already imported", operator.code, existing.version or existing.pk)
        if activate and not existing.is_active:
            with transaction.atomic():
                _activate(existing)
        return ImportResult(existing, created=False)

    problems = Problems()
    with transaction.atomic():
        feed = Feed.objects.create(operator=operator, sha256=archive.sha256)
        counts = _Importer(feed, archive, problems).run()
        feed.stats = {"counts": counts, "warnings": problems.warnings[:200]}
        if len(problems.warnings) > 200:
            feed.stats["warnings_truncated"] = len(problems.warnings)
        feed.save()
        if activate:
            _activate(feed)
    logger.info(
        "Imported %s feed %s: %s (%d warnings)",
        operator.code,
        feed.version or feed.pk,
        ", ".join(f"{n} {k}" for k, n in counts.items()),
        len(problems.warnings),
    )
    if keep:
        prune_feeds(operator, keep)
    return ImportResult(feed, created=True)


def _activate(feed):
    Feed.objects.filter(operator=feed.operator, is_active=True).exclude(pk=feed.pk).update(
        is_active=False
    )
    feed.is_active = True
    feed.save(update_fields=["is_active"])


def prune_feeds(operator: Operator, keep: int):
    """Delete all but the newest ``keep`` feeds, never the active one."""
    feeds = list(operator.feeds.order_by("-is_active", "-imported_at"))
    for old in feeds[max(keep, 1) :]:
        logger.info("Deleting old %s feed %s", operator.code, old)
        delete_feed(old)


# Children before parents. Every one of these tables has a feed_id column, so
# a feed is one DELETE per table instead of Django's row-by-row cascade.
_DELETE_ORDER = (
    FareRule,
    FareAttribute,
    StopTime,
    Trip,
    ServiceDate,
    Service,
    Shape,
    Route,
    Stop,
    Agency,
)


def delete_feed(feed: Feed):
    with transaction.atomic(), connection.cursor() as cursor:
        for model in _DELETE_ORDER:
            cursor.execute(f'DELETE FROM "{model._meta.db_table}" WHERE feed_id = %s', [feed.pk])
        feed.delete()


class _Importer:
    def __init__(self, feed, archive, problems):
        self.feed = feed
        self.archive = archive
        self.problems = problems
        self.counts = {}

    def rows(self, name, required=()):
        return self.archive.rows(name, self.problems, required)

    def run(self):
        for name in sorted(set(self.archive.names) - SUPPORTED):
            self.problems.warn(name, "not used by this app; skipped")
        if self.archive.has("frequencies.txt"):
            self.problems.warn(
                "frequencies.txt",
                "frequency-based service is not supported; those trips "
                "only appear at their template times",
            )
        for required in ("agency.txt", "stops.txt", "routes.txt", "trips.txt", "stop_times.txt"):
            if not self.archive.has(required):
                self.problems.error(required, "required file is missing")
        if not (self.archive.has("calendar.txt") or self.archive.has("calendar_dates.txt")):
            self.problems.error("calendar.txt", "need calendar.txt or calendar_dates.txt")
        self.problems.check()

        self.feed_info()
        self.agencies()
        self.stops()
        self.routes()
        self.services()
        self.shapes()
        self.trips()
        self.stop_times()
        self.fares()
        return self.counts

    def feed_info(self):
        for where, row in self.rows("feed_info.txt"):
            self.feed.publisher_name = row.get("feed_publisher_name", "")
            self.feed.version = row.get("feed_version", "")
            self.feed.start_date = gtfs_date(row, "feed_start_date", where, self.problems)
            self.feed.end_date = gtfs_date(row, "feed_end_date", where, self.problems)
            break
        self.problems.check()

    def agencies(self):
        self.agency_by_id = {}
        name = "agency.txt"
        for where, row in self.rows(name, ("agency_name", "agency_url", "agency_timezone")):
            agency = Agency(
                feed=self.feed,
                agency_id=row.get("agency_id", ""),
                name=need(row, "agency_name", where, self.problems),
                url=need(row, "agency_url", where, self.problems),
                timezone=need(row, "agency_timezone", where, self.problems),
                lang=row.get("agency_lang", ""),
                phone=row.get("agency_phone", ""),
                fare_url=row.get("agency_fare_url", ""),
                email=row.get("agency_email", ""),
            )
            if agency.agency_id in self.agency_by_id:
                self.problems.error(where, f"duplicate agency_id {agency.agency_id!r}")
                continue
            self.agency_by_id[agency.agency_id] = agency
        if not self.agency_by_id:
            self.problems.error(name, "no agencies")
        if len(self.agency_by_id) > 1 and "" in self.agency_by_id:
            self.problems.error(name, "agency_id is required when there are several agencies")
        zones = {a.timezone for a in self.agency_by_id.values()}
        if len(zones) > 1:
            self.problems.error(name, f"agencies disagree on timezone: {sorted(zones)}")
        self.problems.check()

        Agency.objects.bulk_create(self.agency_by_id.values())
        operator = self.feed.operator
        operator.timezone = zones.pop()
        if not operator.name:
            operator.name = next(iter(self.agency_by_id.values())).name
        operator.save()
        self.counts["agencies"] = len(self.agency_by_id)

    def stops(self):
        rows = {}
        for where, row in self.rows("stops.txt", ("stop_id",)):
            stop_id = need(row, "stop_id", where, self.problems)
            if stop_id in rows:
                self.problems.error(where, f"duplicate stop_id {stop_id!r}")
                continue
            location_type = enum(
                row, "location_type", set(LocationType.values), 0, where, self.problems
            )
            lat = decimal(row, "stop_lat", where, self.problems)
            lon = decimal(row, "stop_lon", where, self.problems)
            point = None
            if lat is not None and lon is not None:
                if -90 <= lat <= 90 and -180 <= lon <= 180:
                    point = Point(lon, lat, srid=4326)
                else:
                    self.problems.error(where, f"coordinates out of range: {lat}, {lon}")
            if location_type in (0, 1, 2):
                if not row.get("stop_name"):
                    self.problems.error(where, "stop_name is required for this location_type")
                if point is None:
                    self.problems.error(
                        where, "stop_lat/stop_lon are required for this location_type"
                    )
            rows[stop_id] = (
                where,
                row.get("parent_station", ""),
                Stop(
                    feed=self.feed,
                    stop_id=stop_id,
                    code=row.get("stop_code", ""),
                    name=row.get("stop_name", ""),
                    desc=row.get("stop_desc", ""),
                    point=point,
                    zone_id=row.get("zone_id", ""),
                    url=row.get("stop_url", ""),
                    location_type=location_type,
                    timezone=row.get("stop_timezone", ""),
                    wheelchair_boarding=enum(
                        row, "wheelchair_boarding", {0, 1, 2}, 0, where, self.problems
                    ),
                    platform_code=row.get("platform_code", ""),
                ),
            )

        # A parent must exist and be the right kind of place for its child.
        parent_kinds = {
            LocationType.STOP: {LocationType.STATION},
            LocationType.ENTRANCE: {LocationType.STATION},
            LocationType.GENERIC_NODE: {LocationType.STATION},
            LocationType.BOARDING_AREA: {LocationType.STOP},
        }
        for where, parent_id, stop in rows.values():
            if stop.location_type == LocationType.STATION:
                if parent_id:
                    self.problems.error(where, "a station cannot have a parent_station")
                continue
            if not parent_id:
                if stop.location_type != LocationType.STOP:
                    self.problems.error(where, "parent_station is required for this location_type")
                continue
            parent = rows.get(parent_id)
            if parent is None:
                self.problems.error(where, f"parent_station {parent_id!r} does not exist")
            elif parent[2].location_type not in parent_kinds[stop.location_type]:
                self.problems.error(
                    where,
                    f"parent_station {parent_id!r} is a {parent[2].get_location_type_display()}, "
                    f"which can't contain a {stop.get_location_type_display()}",
                )
        self.problems.check()

        # Insert parents before children so every parent_station_id is known
        # at insert time: stations, then what stations contain, then boarding
        # areas, whose parents are platforms.
        self.stop_by_id = {}
        tiers = ((1,), (0, 2, 3), (4,))
        for tier in tiers:
            batch = []
            for _, parent_id, stop in rows.values():
                if stop.location_type in tier:
                    if parent_id:
                        stop.parent_station = self.stop_by_id[parent_id]
                    batch.append(stop)
            Stop.objects.bulk_create(batch, batch_size=BATCH)
            self.stop_by_id.update((s.stop_id, s) for s in batch)
        self.counts["stops"] = len(self.stop_by_id)

    def routes(self):
        self.route_by_id = {}
        only_agency = (
            next(iter(self.agency_by_id.values())) if len(self.agency_by_id) == 1 else None
        )
        for where, row in self.rows("routes.txt", ("route_id", "route_type")):
            route_id = need(row, "route_id", where, self.problems)
            if route_id in self.route_by_id:
                self.problems.error(where, f"duplicate route_id {route_id!r}")
                continue
            agency_id = row.get("agency_id", "")
            agency = self.agency_by_id.get(agency_id) or (only_agency if not agency_id else None)
            if agency is None:
                self.problems.error(where, f"agency_id {agency_id!r} does not exist")
            if not (row.get("route_short_name") or row.get("route_long_name")):
                self.problems.error(where, "route_short_name or route_long_name is required")
            route_type = integer(row, "route_type", where, self.problems)
            if route_type is not None and not (
                route_type <= 7 or route_type in (11, 12) or 100 <= route_type <= 1799
            ):
                self.problems.error(where, f"route_type={route_type} is not a GTFS route type")
            self.route_by_id[route_id] = Route(
                feed=self.feed,
                route_id=route_id,
                agency=agency,
                short_name=row.get("route_short_name", ""),
                long_name=row.get("route_long_name", ""),
                desc=row.get("route_desc", ""),
                route_type=route_type or 0,
                url=row.get("route_url", ""),
                color=color(row, "route_color", where, self.problems),
                text_color=color(row, "route_text_color", where, self.problems),
                sort_order=integer(row, "route_sort_order", where, self.problems),
            )
        self.problems.check()
        Route.objects.bulk_create(self.route_by_id.values())
        self.counts["routes"] = len(self.route_by_id)

    def services(self):
        self.service_by_id = {}
        days = Service.WEEKDAYS
        for where, row in self.rows(
            "calendar.txt", ("service_id", *days, "start_date", "end_date")
        ):
            service_id = need(row, "service_id", where, self.problems)
            if service_id in self.service_by_id:
                self.problems.error(where, f"duplicate service_id {service_id!r}")
                continue
            flags = {day: enum(row, day, {0, 1}, 0, where, self.problems) == 1 for day in days}
            start = gtfs_date(row, "start_date", where, self.problems)
            end = gtfs_date(row, "end_date", where, self.problems)
            if start is None or end is None:
                self.problems.error(where, "start_date and end_date are required")
            elif end < start:
                self.problems.error(where, f"end_date {end} is before start_date {start}")
            self.service_by_id[service_id] = Service(
                feed=self.feed, service_id=service_id, start_date=start, end_date=end, **flags
            )

        exceptions = []
        seen = set()
        for where, row in self.rows("calendar_dates.txt", ("service_id", "date", "exception_type")):
            service_id = need(row, "service_id", where, self.problems)
            day = gtfs_date(row, "date", where, self.problems)
            kind = enum(
                row, "exception_type", set(ExceptionType.values), None, where, self.problems
            )
            if kind is None:
                self.problems.error(where, "exception_type is required")
            if (service_id, day) in seen:
                self.problems.error(where, f"duplicate date {day} for service {service_id!r}")
                continue
            seen.add((service_id, day))
            if service_id not in self.service_by_id:
                # A service defined only by its exceptions.
                self.service_by_id[service_id] = Service(feed=self.feed, service_id=service_id)
            exceptions.append((service_id, day, kind))
        self.problems.check()

        Service.objects.bulk_create(self.service_by_id.values())
        ServiceDate.objects.bulk_create(
            (
                ServiceDate(
                    feed=self.feed, service=self.service_by_id[sid], date=day, exception_type=kind
                )
                for sid, day, kind in exceptions
            ),
            batch_size=BATCH,
        )
        self.counts["services"] = len(self.service_by_id)
        self.counts["service_dates"] = len(exceptions)

    def shapes(self):
        points = defaultdict(list)
        required = ("shape_id", "shape_pt_lat", "shape_pt_lon", "shape_pt_sequence")
        for where, row in self.rows("shapes.txt", required):
            shape_id = need(row, "shape_id", where, self.problems)
            lat = decimal(row, "shape_pt_lat", where, self.problems)
            lon = decimal(row, "shape_pt_lon", where, self.problems)
            seq = integer(row, "shape_pt_sequence", where, self.problems)
            if None in (lat, lon, seq):
                self.problems.error(where, "shape point needs lat, lon and sequence")
                continue
            points[shape_id].append((seq, lon, lat, where))
        self.problems.check()

        self.shape_by_id = {}
        for shape_id, pts in points.items():
            pts.sort()
            for (a, *_), (b, *_, where) in zip(pts, pts[1:], strict=False):
                if a == b:
                    self.problems.error(
                        where, f"duplicate shape_pt_sequence {b} in shape {shape_id!r}"
                    )
            if len(pts) < 2:
                self.problems.warn("shapes.txt", f"shape {shape_id!r} has one point; dropped")
                continue
            self.shape_by_id[shape_id] = Shape(
                feed=self.feed,
                shape_id=shape_id,
                geometry=LineString([(lon, lat) for _, lon, lat, _ in pts], srid=4326),
            )
        self.problems.check()
        Shape.objects.bulk_create(self.shape_by_id.values(), batch_size=500)
        self.counts["shapes"] = len(self.shape_by_id)

    def trips(self):
        self.trip_by_id = {}
        for where, row in self.rows("trips.txt", ("route_id", "service_id", "trip_id")):
            trip_id = need(row, "trip_id", where, self.problems)
            if trip_id in self.trip_by_id:
                self.problems.error(where, f"duplicate trip_id {trip_id!r}")
                continue
            route = self.route_by_id.get(row.get("route_id", ""))
            if route is None:
                self.problems.error(where, f"route_id {row.get('route_id')!r} does not exist")
            service = self.service_by_id.get(row.get("service_id", ""))
            if service is None:
                self.problems.error(where, f"service_id {row.get('service_id')!r} does not exist")
            shape = None
            if row.get("shape_id"):
                shape = self.shape_by_id.get(row["shape_id"])
                if shape is None:
                    self.problems.warn(
                        where, f"shape_id {row['shape_id']!r} does not exist; ignored"
                    )
            self.trip_by_id[trip_id] = Trip(
                feed=self.feed,
                trip_id=trip_id,
                route=route,
                service=service,
                headsign=row.get("trip_headsign", ""),
                short_name=row.get("trip_short_name", ""),
                direction_id=enum(row, "direction_id", {0, 1}, None, where, self.problems),
                block_id=row.get("block_id", ""),
                shape=shape,
                wheelchair_accessible=enum(
                    row, "wheelchair_accessible", {0, 1, 2}, 0, where, self.problems
                ),
                bikes_allowed=enum(row, "bikes_allowed", {0, 1, 2}, 0, where, self.problems),
            )
        self.problems.check()
        Trip.objects.bulk_create(self.trip_by_id.values(), batch_size=BATCH)
        self.counts["trips"] = len(self.trip_by_id)

    def stop_times(self):
        by_trip = defaultdict(list)
        boardable = {LocationType.STOP, LocationType.BOARDING_AREA}
        required = ("trip_id", "stop_id", "stop_sequence")
        for where, row in self.rows("stop_times.txt", required):
            trip = self.trip_by_id.get(row.get("trip_id", ""))
            if trip is None:
                self.problems.error(where, f"trip_id {row.get('trip_id')!r} does not exist")
                continue
            stop = self.stop_by_id.get(row.get("stop_id", ""))
            if stop is None:
                self.problems.error(where, f"stop_id {row.get('stop_id')!r} does not exist")
                continue
            if stop.location_type not in boardable:
                self.problems.error(
                    where,
                    f"stop_id {stop.stop_id!r} is a {stop.get_location_type_display()}; "
                    "trips can only call at stops/platforms or boarding areas",
                )
            seq = integer(row, "stop_sequence", where, self.problems)
            if seq is None:
                self.problems.error(where, "stop_sequence is required")
                continue
            arrival = gtfs_time(row, "arrival_time", where, self.problems)
            departure = gtfs_time(row, "departure_time", where, self.problems)
            # The spec lets a timed stop give just one of the two.
            if arrival is None:
                arrival = departure
            if departure is None:
                departure = arrival
            if arrival is not None and departure < arrival:
                self.problems.error(where, "departure_time is before arrival_time")
            timepoint = enum(row, "timepoint", {0, 1}, None, where, self.problems)
            if timepoint is None:
                timepoint = 1 if arrival is not None else 0
            by_trip[trip.trip_id].append(
                (
                    seq,
                    where,
                    StopTime(
                        feed=self.feed,
                        trip=trip,
                        stop=stop,
                        stop_sequence=seq,
                        arrival_secs=arrival,
                        departure_secs=departure,
                        stop_headsign=row.get("stop_headsign", ""),
                        pickup_type=enum(row, "pickup_type", {0, 1, 2, 3}, 0, where, self.problems),
                        drop_off_type=enum(
                            row, "drop_off_type", {0, 1, 2, 3}, 0, where, self.problems
                        ),
                        shape_dist_traveled=decimal(
                            row, "shape_dist_traveled", where, self.problems
                        ),
                        timepoint=timepoint == 1,
                    ),
                )
            )

        for trip_id, calls in by_trip.items():
            calls.sort(key=lambda c: c[0])
            for (a, _, _), (b, where, _) in zip(calls, calls[1:], strict=False):
                if a == b:
                    self.problems.error(where, f"duplicate stop_sequence {b} in trip {trip_id!r}")
            if len(calls) < 2:
                self.problems.warn("stop_times.txt", f"trip {trip_id!r} has fewer than two stops")
            first, last = calls[0], calls[-1]
            for _, where, st in (first, last):
                if st.arrival_secs is None:
                    self.problems.error(
                        where, f"first and last stops of trip {trip_id!r} must be timed"
                    )
            previous = None
            for _, where, st in calls:
                if st.arrival_secs is None:
                    continue
                if previous is not None and st.arrival_secs < previous:
                    self.problems.error(where, f"trip {trip_id!r} goes back in time here")
                previous = st.departure_secs
        untimed = set(self.trip_by_id) - set(by_trip)
        for trip_id in sorted(untimed)[:20]:
            self.problems.warn("stop_times.txt", f"trip {trip_id!r} has no stop times")
        self.problems.check()

        interpolated = sum(_interpolate([st for _, _, st in calls]) for calls in by_trip.values())
        if interpolated:
            self.problems.warn(
                "stop_times.txt", f"interpolated times for {interpolated} untimed stops"
            )

        total = 0
        batch = []
        for calls in by_trip.values():
            batch.extend(st for _, _, st in calls)
            if len(batch) >= BATCH:
                StopTime.objects.bulk_create(batch)
                total += len(batch)
                batch = []
        StopTime.objects.bulk_create(batch)
        self.counts["stop_times"] = total + len(batch)

    def fares(self):
        fare_by_id = {}
        required = ("fare_id", "price", "currency_type", "payment_method", "transfers")
        for where, row in self.rows("fare_attributes.txt", required):
            fare_id = need(row, "fare_id", where, self.problems)
            if fare_id in fare_by_id:
                self.problems.error(where, f"duplicate fare_id {fare_id!r}")
                continue
            try:
                price = Decimal(row.get("price", ""))
            except InvalidOperation:
                self.problems.error(where, f"price={row.get('price')!r} is not a number")
                price = Decimal(0)
            agency_id = row.get("agency_id", "")
            agency = self.agency_by_id.get(agency_id) if agency_id else None
            if agency_id and agency is None:
                self.problems.error(where, f"agency_id {agency_id!r} does not exist")
            fare_by_id[fare_id] = FareAttribute(
                feed=self.feed,
                fare_id=fare_id,
                agency=agency,
                price=price,
                currency_type=need(row, "currency_type", where, self.problems).upper(),
                payment_method=enum(row, "payment_method", {0, 1}, 0, where, self.problems),
                # Blank means unlimited transfers, which is why this is nullable.
                transfers=enum(row, "transfers", {0, 1, 2}, None, where, self.problems),
                transfer_duration=integer(row, "transfer_duration", where, self.problems),
            )
        rules = []
        for where, row in self.rows("fare_rules.txt", ("fare_id",)):
            fare = fare_by_id.get(row.get("fare_id", ""))
            if fare is None:
                self.problems.error(where, f"fare_id {row.get('fare_id')!r} does not exist")
                continue
            route = None
            if row.get("route_id"):
                route = self.route_by_id.get(row["route_id"])
                if route is None:
                    self.problems.error(where, f"route_id {row['route_id']!r} does not exist")
            rules.append(
                FareRule(
                    feed=self.feed,
                    fare=fare,
                    route=route,
                    origin_id=row.get("origin_id", ""),
                    destination_id=row.get("destination_id", ""),
                    contains_id=row.get("contains_id", ""),
                )
            )
        self.problems.check()
        FareAttribute.objects.bulk_create(fare_by_id.values())
        FareRule.objects.bulk_create(rules, batch_size=BATCH)
        self.counts["fares"] = len(fare_by_id)
        self.counts["fare_rules"] = len(rules)


def _interpolate(calls) -> int:
    """Fill untimed stops between two timed ones, in place. Returns how many.

    Spaced by shape_dist_traveled when every stop in the gap has it, else
    evenly. These rows keep timepoint=False, so they read as approximate.
    """
    filled = 0
    timed = [i for i, st in enumerate(calls) if st.arrival_secs is not None]
    for a, b in zip(timed, timed[1:], strict=False):
        if b - a < 2:
            continue
        start, end = calls[a].departure_secs, calls[b].arrival_secs
        span = calls[a : b + 1]
        dists = [st.shape_dist_traveled for st in span]
        use_dist = None not in dists and dists[-1] > dists[0]
        for k in range(a + 1, b):
            if use_dist:
                fraction = (dists[k - a] - dists[0]) / (dists[-1] - dists[0])
            else:
                fraction = (k - a) / (b - a)
            secs = round(start + (end - start) * fraction)
            calls[k].arrival_secs = calls[k].departure_secs = secs
            calls[k].timepoint = False
            filled += 1
    return filled
