"""Import a static GTFS archive as a new Feed.

The whole import runs in one transaction: a feed either lands complete and
valid, or not at all. Structural problems (missing required fields, dangling
references, times running backwards) are errors that abort the import with
every problem listed by file and line. Cosmetic ones (a malformed route
color, a file this app doesn't use) are warnings recorded on the feed.

A FeedFilter imports part of a feed - some agencies, and for each of them
some route types - which is how the 41-agency regional feed becomes just the
agencies this app shows. Everything not needed by a kept trip (stops,
services, shapes) is left out too. A reference to something filtered out is
skipped; a reference to something that doesn't exist at all is still an
error.

stop_times.txt is the one big file (millions of rows regionally), so it is
streamed into a temporary table with COPY and checked with SQL rather than
held in memory. Every other file is small enough for Python.

Archives are identified by hash (plus the filter), so re-importing an
unchanged download is a no-op.
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
    Place,
    Route,
    Service,
    ServiceDate,
    Shape,
    Stop,
    StopTime,
    Trip,
)

from .places import build_places
from .times import parse_gtfs_date, parse_gtfs_time

logger = logging.getLogger(__name__)

BATCH = 5000
MAX_ERRORS = 50
# SQL checks report at most this many offending rows each.
SQL_ERROR_LIMIT = 200

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


@dataclass(frozen=True)
class FeedFilter:
    """Which agencies to import, and optionally which route types of each.

    Written as a spec string: ``"SF:0,BA,SM,CT"`` keeps BART, SamTrans and
    Caltrain whole, and only Muni's light rail and streetcars (route_type 0).
    Join several types with ``+``, e.g. ``SF:0+5`` adds the cable cars.
    """

    agencies: tuple[tuple[str, frozenset[int] | None], ...]

    @classmethod
    def parse(cls, spec: str | None) -> "FeedFilter | None":
        if not spec or not spec.strip():
            return None
        agencies = {}
        for part in spec.split(","):
            part = part.strip()
            if not part:
                continue
            agency, _, types = part.partition(":")
            try:
                route_types = frozenset(int(t) for t in types.split("+")) if types else None
            except ValueError:
                raise ValueError(f"bad route types in feed filter {part!r}") from None
            agencies[agency.strip()] = route_types
        return cls(tuple(sorted(agencies.items(), key=lambda kv: kv[0])))

    @property
    def spec(self) -> str:
        return ",".join(
            agency + (":" + "+".join(str(t) for t in sorted(types)) if types else "")
            for agency, types in self.agencies
        )

    def keeps_agency(self, agency_id) -> bool:
        return any(agency == agency_id for agency, _ in self.agencies)

    def keeps_route(self, agency_id, route_type) -> bool:
        for agency, types in self.agencies:
            if agency == agency_id:
                return types is None or route_type in types
        return False


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

    def rows(self, name, problems, required=(), only=None):
        """Yield (location, row) for each data row, with keys and values stripped.

        ``only=(column, predicate)`` skips rows whose raw value in ``column``
        fails the predicate before building a dict for them, which matters
        when most of a multi-million-row file is being filtered out.
        """
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
            only_index, only_test = None, None
            if only is not None and only[0] in header:
                only_index, only_test = header.index(only[0]), only[1]
            for values in reader:
                if only_index is not None and only_index < len(values):
                    if not only_test(values[only_index].strip()):
                        continue
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


def import_feed(
    operator: Operator, source, *, activate=True, keep=None, only: FeedFilter | None = None
) -> ImportResult:
    archive = Archive(source)
    sha256 = archive.sha256
    if only is not None:
        # The same archive filtered differently is a different feed.
        sha256 = hashlib.sha256(f"{sha256}|{only.spec}".encode()).hexdigest()
    existing = Feed.objects.filter(operator=operator, sha256=sha256).first()
    if existing:
        logger.info("%s feed %s already imported", operator.code, existing.version or existing.pk)
        if activate and not existing.is_active:
            with transaction.atomic():
                _activate(existing)
        return ImportResult(existing, created=False)

    problems = Problems()
    with transaction.atomic():
        feed = Feed.objects.create(operator=operator, sha256=sha256)
        counts = _Importer(feed, archive, problems, only).run()
        feed.stats = {"counts": counts, "warnings": problems.warnings[:200]}
        if only is not None:
            feed.stats["filter"] = only.spec
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
    Stop,
    Place,
    Route,
    Agency,
)


def delete_feed(feed: Feed):
    with transaction.atomic(), connection.cursor() as cursor:
        # The place-route links are the one table without a feed_id.
        cursor.execute(
            f'DELETE FROM "{Place.routes.through._meta.db_table}" WHERE place_id IN '
            f'(SELECT id FROM "{Place._meta.db_table}" WHERE feed_id = %s)',
            [feed.pk],
        )
        for model in _DELETE_ORDER:
            cursor.execute(f'DELETE FROM "{model._meta.db_table}" WHERE feed_id = %s', [feed.pk])
        feed.delete()


class _Importer:
    """Reads files in dependency order.

    Filtering runs top-down - agencies, routes, trips - and then the kept
    trips decide which services, shapes and stops are needed, so the order
    is: parse what trips refer to, decide the trips, then save only what they
    use.
    """

    def __init__(self, feed, archive, problems, only):
        self.feed = feed
        self.archive = archive
        self.problems = problems
        self.only = only
        self.counts = {}

    def rows(self, name, required=(), only=None):
        return self.archive.rows(name, self.problems, required, only)

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
        self.routes()
        self.parse_services()
        self.parse_trips()
        self.stops()
        self.save_services()
        self.shapes()
        self.save_trips()
        self.stop_times()
        self.fares()
        self.counts["places"] = build_places(self.feed)
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
        self.all_agency_ids = set()
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
            if agency.agency_id in self.all_agency_ids:
                self.problems.error(where, f"duplicate agency_id {agency.agency_id!r}")
                continue
            self.all_agency_ids.add(agency.agency_id)
            if self.only is None or self.only.keeps_agency(agency.agency_id):
                self.agency_by_id[agency.agency_id] = agency
        if not self.all_agency_ids:
            self.problems.error(name, "no agencies")
        if len(self.all_agency_ids) > 1 and "" in self.all_agency_ids:
            self.problems.error(name, "agency_id is required when there are several agencies")
        if self.only is not None:
            for agency_id, _ in self.only.agencies:
                if agency_id not in self.all_agency_ids:
                    self.problems.error(
                        name,
                        f"the feed filter names agency {agency_id!r}, which isn't in this feed",
                    )
        zones = {a.timezone for a in self.agency_by_id.values()}
        if len(zones) > 1:
            self.problems.error(name, f"agencies disagree on timezone: {sorted(zones)}")
        self.problems.check()

        Agency.objects.bulk_create(self.agency_by_id.values())
        operator = self.feed.operator
        operator.timezone = zones.pop()
        if not operator.name:
            agencies = list(self.agency_by_id.values())
            operator.name = agencies[0].name if len(agencies) == 1 else operator.code
        operator.save()
        self.counts["agencies"] = len(self.agency_by_id)

    def routes(self):
        self.route_by_id = {}
        self.all_route_ids = set()
        only_agency = len(self.all_agency_ids) == 1
        for where, row in self.rows("routes.txt", ("route_id", "route_type")):
            route_id = need(row, "route_id", where, self.problems)
            if route_id in self.all_route_ids:
                self.problems.error(where, f"duplicate route_id {route_id!r}")
                continue
            self.all_route_ids.add(route_id)
            agency_id = row.get("agency_id", "")
            if not agency_id and only_agency:
                agency_id = next(iter(self.all_agency_ids))
            if agency_id not in self.all_agency_ids:
                self.problems.error(where, f"agency_id {row.get('agency_id')!r} does not exist")
            if not (row.get("route_short_name") or row.get("route_long_name")):
                self.problems.error(where, "route_short_name or route_long_name is required")
            route_type = integer(row, "route_type", where, self.problems)
            if route_type is not None and not (
                route_type <= 7 or route_type in (11, 12) or 100 <= route_type <= 1799
            ):
                self.problems.error(where, f"route_type={route_type} is not a GTFS route type")
            agency = self.agency_by_id.get(agency_id)
            if agency is None or (
                self.only is not None and not self.only.keeps_route(agency_id, route_type)
            ):
                continue
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

    def parse_services(self):
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

        self.exceptions = []
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
            self.exceptions.append((service_id, day, kind))
        self.problems.check()

    def parse_trips(self):
        """Decide which trips are kept. Their services, shapes and stops follow."""
        self.trip_by_id = {}
        self.trip_shape = {}
        self.all_trip_ids = set()
        for where, row in self.rows("trips.txt", ("route_id", "service_id", "trip_id")):
            trip_id = need(row, "trip_id", where, self.problems)
            if trip_id in self.all_trip_ids:
                self.problems.error(where, f"duplicate trip_id {trip_id!r}")
                continue
            self.all_trip_ids.add(trip_id)
            route_id = row.get("route_id", "")
            if route_id not in self.all_route_ids:
                self.problems.error(where, f"route_id {route_id!r} does not exist")
            service = self.service_by_id.get(row.get("service_id", ""))
            if service is None:
                self.problems.error(where, f"service_id {row.get('service_id')!r} does not exist")
            route = self.route_by_id.get(route_id)
            if route is None:
                continue
            if row.get("shape_id"):
                self.trip_shape[trip_id] = (where, row["shape_id"])
            self.trip_by_id[trip_id] = Trip(
                feed=self.feed,
                trip_id=trip_id,
                route=route,
                service=service,
                headsign=row.get("trip_headsign", ""),
                short_name=row.get("trip_short_name", ""),
                direction_id=enum(row, "direction_id", {0, 1}, None, where, self.problems),
                block_id=row.get("block_id", ""),
                wheelchair_accessible=enum(
                    row, "wheelchair_accessible", {0, 1, 2}, 0, where, self.problems
                ),
                bikes_allowed=enum(row, "bikes_allowed", {0, 1, 2}, 0, where, self.problems),
            )
        self.problems.check()

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
        self.all_stop_ids = set(rows)

        if self.only is not None:
            # Only the stops kept trips call at, and the stations they belong to.
            used = self._stops_used_by_kept_trips()
            wanted = set()
            for stop_id in used & self.all_stop_ids:
                while stop_id and stop_id not in wanted:
                    wanted.add(stop_id)
                    stop_id = rows[stop_id][1]
            rows = {stop_id: rows[stop_id] for stop_id in rows if stop_id in wanted}

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

    def _stops_used_by_kept_trips(self):
        kept = self.trip_by_id
        used = set()
        for _, row in self.rows("stop_times.txt", only=("trip_id", kept.__contains__)):
            used.add(row.get("stop_id", ""))
        return used

    def save_services(self):
        if self.only is not None:
            used = {trip.service.service_id for trip in self.trip_by_id.values()}
            self.service_by_id = {k: v for k, v in self.service_by_id.items() if k in used}
            self.exceptions = [e for e in self.exceptions if e[0] in used]
        Service.objects.bulk_create(self.service_by_id.values())
        for trip in self.trip_by_id.values():
            # Re-point at the saved instance, which now has a primary key.
            trip.service = self.service_by_id[trip.service.service_id]
        ServiceDate.objects.bulk_create(
            (
                ServiceDate(
                    feed=self.feed, service=self.service_by_id[sid], date=day, exception_type=kind
                )
                for sid, day, kind in self.exceptions
            ),
            batch_size=BATCH,
        )
        self.counts["services"] = len(self.service_by_id)
        self.counts["service_dates"] = len(self.exceptions)

        if self.feed.start_date is None and self.feed.end_date is None:
            # No feed_info dates (511's regional feed ships an empty one): the
            # feed is valid for as long as its calendar says something runs.
            days = [d for s in self.service_by_id.values() for d in (s.start_date, s.end_date)]
            days += [day for _, day, kind in self.exceptions if kind == ExceptionType.ADDED]
            days = [d for d in days if d is not None]
            if days:
                self.feed.start_date, self.feed.end_date = min(days), max(days)

    def shapes(self):
        wanted = None
        if self.only is not None:
            wanted = {shape_id for _, shape_id in self.trip_shape.values()}
        all_shape_ids = set()
        points = defaultdict(list)
        required = ("shape_id", "shape_pt_lat", "shape_pt_lon", "shape_pt_sequence")
        for where, row in self.rows("shapes.txt", required):
            shape_id = need(row, "shape_id", where, self.problems)
            all_shape_ids.add(shape_id)
            if wanted is not None and shape_id not in wanted:
                continue
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

        for trip_id, (where, shape_id) in self.trip_shape.items():
            shape = self.shape_by_id.get(shape_id)
            if shape is None and shape_id not in all_shape_ids:
                self.problems.warn(where, f"shape_id {shape_id!r} does not exist; ignored")
            self.trip_by_id[trip_id].shape = shape

    def save_trips(self):
        Trip.objects.bulk_create(self.trip_by_id.values(), batch_size=BATCH)
        self.counts["trips"] = len(self.trip_by_id)

    def stop_times(self):
        """Stream rows through per-row checks into a temp table, then check trips in SQL."""
        boardable = {LocationType.STOP, LocationType.BOARDING_AREA}
        required = ("trip_id", "stop_id", "stop_sequence")
        kept, everywhere = self.trip_by_id, self.all_trip_ids

        def wanted(trip_id):
            # Filtered-out trips are skipped cheaply; unknown ids still get an error.
            return trip_id in kept or trip_id not in everywhere

        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS stage_stop_time")
            cursor.execute(
                """
                CREATE TEMP TABLE stage_stop_time (
                    line integer, trip_pk bigint, trip_id text, stop_pk bigint,
                    seq integer, arr integer, dep integer, headsign text,
                    pickup smallint, dropoff smallint, dist double precision,
                    timepoint smallint
                ) ON COMMIT DROP
                """
            )
            columns = (
                "line, trip_pk, trip_id, stop_pk, seq, arr, dep, headsign, "
                "pickup, dropoff, dist, timepoint"
            )
            with cursor.cursor.copy(f"COPY stage_stop_time ({columns}) FROM STDIN") as copy:
                for where, row in self.rows("stop_times.txt", required, only=("trip_id", wanted)):
                    trip = kept.get(row.get("trip_id", ""))
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
                    copy.write_row(
                        (
                            int(where.rsplit(":", 1)[1]),
                            trip.pk,
                            trip.trip_id,
                            stop.pk,
                            seq,
                            arrival,
                            departure,
                            row.get("stop_headsign", ""),
                            enum(row, "pickup_type", {0, 1, 2, 3}, 0, where, self.problems),
                            enum(row, "drop_off_type", {0, 1, 2, 3}, 0, where, self.problems),
                            decimal(row, "shape_dist_traveled", where, self.problems),
                            enum(row, "timepoint", {0, 1}, None, where, self.problems),
                        )
                    )
                    if len(self.problems.errors) > SQL_ERROR_LIMIT:
                        break
            self.problems.check()
            self._check_trips(cursor)
            self.counts["stop_times"] = self._insert_stop_times(cursor)

    def _sql_errors(self, cursor, sql, message):
        cursor.execute(sql + f" LIMIT {SQL_ERROR_LIMIT}")
        for line, trip_id, *extra in cursor.fetchall():
            self.problems.error(f"stop_times.txt:{line}", message(trip_id, *extra))

    def _check_trips(self, cursor):
        """The rules that need a whole trip at once, as set-based SQL."""
        self._sql_errors(
            cursor,
            """
            SELECT max(line), trip_id, seq FROM stage_stop_time
            GROUP BY trip_pk, trip_id, seq HAVING count(*) > 1 ORDER BY 1
            """,
            lambda trip_id, seq: f"duplicate stop_sequence {seq} in trip {trip_id!r}",
        )
        # Ordering is meaningless with duplicate sequence numbers; stop here.
        self.problems.check()
        self._sql_errors(
            cursor,
            """
            SELECT line, trip_id FROM (
                SELECT line, trip_id, arr,
                       row_number() OVER (PARTITION BY trip_pk ORDER BY seq) AS rn,
                       count(*) OVER (PARTITION BY trip_pk) AS n
                FROM stage_stop_time
            ) t WHERE arr IS NULL AND (rn = 1 OR rn = n) ORDER BY 1
            """,
            lambda trip_id: f"first and last stops of trip {trip_id!r} must be timed",
        )
        self._sql_errors(
            cursor,
            """
            SELECT line, trip_id FROM (
                SELECT line, trip_id, arr,
                       lag(dep) OVER (PARTITION BY trip_pk ORDER BY seq) AS previous
                FROM stage_stop_time WHERE arr IS NOT NULL
            ) t WHERE arr < previous ORDER BY 1
            """,
            lambda trip_id: f"trip {trip_id!r} goes back in time here",
        )
        self.problems.check()

        cursor.execute(
            """
            SELECT trip_id FROM stage_stop_time GROUP BY trip_pk, trip_id
            HAVING count(*) < 2 ORDER BY trip_id LIMIT 20
            """
        )
        for (trip_id,) in cursor.fetchall():
            self.problems.warn("stop_times.txt", f"trip {trip_id!r} has fewer than two stops")
        cursor.execute(
            f"""
            SELECT t.trip_id FROM "{Trip._meta.db_table}" t
            WHERE t.feed_id = %s
              AND NOT EXISTS (SELECT 1 FROM stage_stop_time s WHERE s.trip_pk = t.id)
            ORDER BY t.trip_id LIMIT 20
            """,
            [self.feed.pk],
        )
        for (trip_id,) in cursor.fetchall():
            self.problems.warn("stop_times.txt", f"trip {trip_id!r} has no stop times")

    def _insert_stop_times(self, cursor) -> int:
        """Move staged rows into the real table, interpolating untimed stops.

        An untimed stop between two timed ones gets a time spaced by
        shape_dist_traveled when the stop and both neighbours have it, else
        evenly by position. Those rows get timepoint=false, so they read as
        approximate.
        """
        cursor.execute("SELECT count(*) FROM stage_stop_time WHERE arr IS NULL")
        untimed = cursor.fetchone()[0]
        cursor.execute(
            f"""
            WITH ordered AS (
                SELECT s.*,
                       row_number() OVER w AS rn,
                       max(CASE WHEN arr IS NOT NULL THEN seq END) OVER (
                           w ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS prev_seq,
                       min(CASE WHEN arr IS NOT NULL THEN seq END) OVER (
                           w ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING) AS next_seq
                FROM stage_stop_time s
                WINDOW w AS (PARTITION BY trip_pk ORDER BY seq)
            ),
            filled AS (
                SELECT o.*,
                       CASE WHEN o.arr IS NOT NULL THEN NULL
                       ELSE round(p.dep + (n.arr - p.dep) * greatest(0.0, least(1.0,
                           CASE WHEN o.dist IS NOT NULL AND p.dist IS NOT NULL
                                     AND n.dist IS NOT NULL AND n.dist > p.dist
                                THEN (o.dist - p.dist) / (n.dist - p.dist)
                                ELSE (o.rn - p.rn)::double precision / (n.rn - p.rn)
                           END)))::integer
                       END AS guess
                FROM ordered o
                LEFT JOIN ordered p ON p.trip_pk = o.trip_pk AND p.seq = o.prev_seq
                LEFT JOIN ordered n ON n.trip_pk = o.trip_pk AND n.seq = o.next_seq
            )
            INSERT INTO "{StopTime._meta.db_table}" (
                feed_id, trip_id, stop_id, stop_sequence, arrival_secs, departure_secs,
                stop_headsign, pickup_type, drop_off_type, shape_dist_traveled, timepoint
            )
            SELECT %s, trip_pk, stop_pk, seq, coalesce(arr, guess), coalesce(dep, guess),
                   headsign, pickup, dropoff, dist,
                   CASE WHEN arr IS NULL THEN false ELSE coalesce(timepoint, 1) = 1 END
            FROM filled
            """,
            [self.feed.pk],
        )
        inserted = cursor.rowcount
        if untimed:
            self.problems.warn("stop_times.txt", f"interpolated times for {untimed} untimed stops")
        return inserted

    def fares(self):
        fare_by_id = {}
        all_fare_ids = set()
        required = ("fare_id", "price", "currency_type", "payment_method", "transfers")
        for where, row in self.rows("fare_attributes.txt", required):
            fare_id = need(row, "fare_id", where, self.problems)
            if fare_id in all_fare_ids:
                self.problems.error(where, f"duplicate fare_id {fare_id!r}")
                continue
            all_fare_ids.add(fare_id)
            try:
                price = Decimal(row.get("price", ""))
            except InvalidOperation:
                self.problems.error(where, f"price={row.get('price')!r} is not a number")
                price = Decimal(0)
            agency_id = row.get("agency_id", "")
            if agency_id and agency_id not in self.all_agency_ids:
                self.problems.error(where, f"agency_id {agency_id!r} does not exist")
            if agency_id and agency_id not in self.agency_by_id:
                continue
            fare_by_id[fare_id] = FareAttribute(
                feed=self.feed,
                fare_id=fare_id,
                agency=self.agency_by_id.get(agency_id) if agency_id else None,
                price=price,
                currency_type=need(row, "currency_type", where, self.problems).upper(),
                payment_method=enum(row, "payment_method", {0, 1}, 0, where, self.problems),
                # Blank means unlimited transfers, which is why this is nullable.
                transfers=enum(row, "transfers", {0, 1, 2}, None, where, self.problems),
                transfer_duration=integer(row, "transfer_duration", where, self.problems),
            )
        rules = []
        for where, row in self.rows("fare_rules.txt", ("fare_id",)):
            fare_id = row.get("fare_id", "")
            if fare_id not in all_fare_ids:
                self.problems.error(where, f"fare_id {fare_id!r} does not exist")
                continue
            route = None
            if row.get("route_id"):
                if row["route_id"] not in self.all_route_ids:
                    self.problems.error(where, f"route_id {row['route_id']!r} does not exist")
                    continue
                route = self.route_by_id.get(row["route_id"])
                if route is None:
                    continue  # filtered out
            if fare_id not in fare_by_id:
                continue  # its agency is filtered out
            rules.append(
                FareRule(
                    feed=self.feed,
                    fare=fare_by_id[fare_id],
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
