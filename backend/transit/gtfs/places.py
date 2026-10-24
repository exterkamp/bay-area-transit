"""Derive places from an imported feed's stops and stop times.

See transit.models.places for what a place is. Runs inside the import
transaction, after stop times, and again from a migration for feeds imported
before places existed, which is why the models are parameters.
"""

import math
import re
from collections import Counter, defaultdict

from django.contrib.gis.geos import Point
from django.db import connection

from transit.models import Accessibility, LocationType, Place, PlaceKind, Stop

# Same-named free-standing stops closer than this (to any stop already in the
# group) are one place. Opposite sides of a street are 20-90 m apart in 511's
# data; same-named stops in different towns are kilometers apart.
GROUP_RADIUS_M = 300


def build_places(feed, place_model=Place, stop_model=Stop) -> int:
    """Create the feed's places, point its stops at them and link their routes."""
    stops = list(
        stop_model.objects.filter(
            feed=feed, location_type__in=[LocationType.STOP, LocationType.STATION]
        ).only(
            "stop_id",
            "name",
            "point",
            "location_type",
            "parent_station_id",
            "zone_id",
            "wheelchair_boarding",
        )
    )
    members = []  # (Place, [Stop]) in creation order
    stations = {s.pk: s for s in stops if s.location_type == LocationType.STATION}
    children = defaultdict(list)
    loose = defaultdict(list)
    for s in stops:
        if s.location_type == LocationType.STATION:
            continue
        if s.parent_station_id in stations:
            children[s.parent_station_id].append(s)
        elif not s.parent_station_id:
            loose[_normalized(s.name)].append(s)

    for station in stations.values():
        place = place_model(
            feed=feed,
            place_id=station.stop_id,
            name=station.name,
            kind=PlaceKind.STATION,
            point=station.point,
            zone_id=station.zone_id,
            wheelchair_boarding=station.wheelchair_boarding,
        )
        members.append((place, [station, *children[station.pk]]))

    for group in loose.values():
        for cluster in _clusters(group):
            first = min(cluster, key=lambda s: s.stop_id)
            place = place_model(
                feed=feed,
                place_id=first.stop_id,
                name=first.name,
                kind=PlaceKind.STOP,
                point=Point(
                    sum(s.point.x for s in cluster) / len(cluster),
                    sum(s.point.y for s in cluster) / len(cluster),
                    srid=4326,
                ),
                zone_id=_shared(s.zone_id for s in cluster) or "",
                wheelchair_boarding=_shared(s.wheelchair_boarding for s in cluster)
                or Accessibility.UNKNOWN,
            )
            members.append((place, cluster))

    place_model.objects.bulk_create([place for place, _ in members], batch_size=2000)
    updated = []
    for place, group in members:
        for s in group:
            s.place = place
            updated.append(s)
    stop_model.objects.bulk_update(updated, ["place"], batch_size=5000)
    _link_routes(feed, place_model, stop_model)
    return len(members)


def _link_routes(feed, place_model, stop_model):
    through = place_model.routes.through._meta.db_table
    stop_time = stop_model.stop_times.field.model._meta.db_table
    trip = stop_model.stop_times.field.model.trip.field.related_model._meta.db_table
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            INSERT INTO {through} (place_id, route_id)
            SELECT DISTINCT s.place_id, t.route_id
            FROM {stop_time} st
            JOIN {stop_model._meta.db_table} s ON s.id = st.stop_id
            JOIN {trip} t ON t.id = st.trip_id
            WHERE st.feed_id = %s AND s.place_id IS NOT NULL
            """,
            [feed.pk],
        )


def _normalized(name):
    return re.sub(r"\s+", " ", name).strip().casefold()


def _shared(values):
    """The value every member has, or None."""
    counts = Counter(values)
    return next(iter(counts)) if len(counts) == 1 else None


def _clusters(stops):
    """Single-linkage groups of stops within GROUP_RADIUS_M of each other."""
    remaining = sorted(stops, key=lambda s: s.stop_id)
    clusters = []
    while remaining:
        cluster = [remaining.pop(0)]
        grew = True
        while grew:
            near = [
                s
                for s in remaining
                if any(_meters(s.point, c.point) <= GROUP_RADIUS_M for c in cluster)
            ]
            grew = bool(near)
            for s in near:
                remaining.remove(s)
            cluster.extend(near)
        clusters.append(cluster)
    return clusters


def _meters(a, b):
    """Equirectangular distance: plenty for a few hundred meters."""
    lat = math.radians((a.y + b.y) / 2)
    dx = math.radians(b.x - a.x) * math.cos(lat)
    dy = math.radians(b.y - a.y)
    return 6_371_000 * math.hypot(dx, dy)
