"""Places: what a rider picks as an origin, destination or board.

Not a GTFS record. The importer derives places from stops.txt after the
stop times are in: a station is one place with its platforms, and
free-standing stops that share a name and stand within a short walk of each
other (the two sides of a street) are another. Without that grouping a
rider who picked the wrong side of the street would get no trips.
"""

from django.contrib.gis.db import models
from django.contrib.postgres.indexes import GinIndex
from django.db.models import Q

from .gtfs import Accessibility, Route, _in


class PlaceKind(models.TextChoices):
    STATION = "station", "Station"
    STOP = "stop", "Stop group"


class Place(models.Model):
    feed = models.ForeignKey("Feed", on_delete=models.CASCADE, related_name="places")
    # The station's stop_id, or the lowest stop_id in a group: stable across
    # feed versions as long as 511 keeps its stop ids.
    place_id = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    kind = models.CharField(max_length=16, choices=PlaceKind.choices)
    point = models.PointField(srid=4326)
    zone_id = models.CharField(max_length=255, blank=True)
    wheelchair_boarding = models.PositiveSmallIntegerField(
        choices=Accessibility.choices, default=Accessibility.UNKNOWN
    )
    # Routes with a trip that calls at one of the place's stops.
    routes = models.ManyToManyField(Route, related_name="places", blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["feed", "place_id"], name="place_unique_per_feed"),
            models.CheckConstraint(condition=~Q(name=""), name="place_needs_a_name"),
            models.CheckConstraint(condition=_in("kind", PlaceKind), name="place_kind_valid"),
            models.CheckConstraint(
                condition=_in("wheelchair_boarding", Accessibility),
                name="place_wheelchair_boarding_valid",
            ),
        ]
        indexes = [GinIndex(fields=["name"], opclasses=["gin_trgm_ops"], name="place_name_trgm")]

    def __str__(self):
        return self.name

    @property
    def lat(self):
        return self.point.y

    @property
    def lon(self):
        return self.point.x
