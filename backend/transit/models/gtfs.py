"""Static GTFS, one row per record of one imported feed.

Hardening rules every model here follows:

- Every table carries ``feed`` directly, even where it is derivable (stop
  times, service dates), so GTFS ids are unique *per feed* by constraint and a
  whole feed can be deleted table by table without joins.
- Enumerations are integer choices matching the GTFS spec values, and a check
  constraint keeps the column inside them. Optional enums with a "no
  information" value (0) default to it instead of being nullable.
- Times of day are seconds after the service day's start (GTFS "noon minus
  12h"), so 25:10:00 is 90600 rather than being squeezed into a time type.
- Anything the spec makes conditionally required is a check constraint when
  it is local to the row; cross-row rules (a parent station must be a
  station, times must not go backwards along a trip) are enforced by the
  importer, which is the only writer.
"""

from django.contrib.gis.db import models
from django.db.models import F, Q

HEX_COLOR = r"^([0-9A-Fa-f]{6})?$"


def _in(field, choices):
    return Q(**{f"{field}__in": [value for value, _ in choices.choices]})


class LocationType(models.IntegerChoices):
    STOP = 0, "Stop or platform"
    STATION = 1, "Station"
    ENTRANCE = 2, "Entrance or exit"
    GENERIC_NODE = 3, "Generic node"
    BOARDING_AREA = 4, "Boarding area"


class Accessibility(models.IntegerChoices):
    UNKNOWN = 0, "No information"
    ACCESSIBLE = 1, "Accessible"
    INACCESSIBLE = 2, "Not accessible"


class PickupDropOff(models.IntegerChoices):
    REGULAR = 0, "Regularly scheduled"
    NONE = 1, "Not available"
    PHONE = 2, "Phone agency"
    COORDINATE = 3, "Coordinate with driver"


class ExceptionType(models.IntegerChoices):
    ADDED = 1, "Service added"
    REMOVED = 2, "Service removed"


class Agency(models.Model):
    """agency.txt"""

    feed = models.ForeignKey("Feed", on_delete=models.CASCADE, related_name="agencies")
    agency_id = models.CharField(max_length=255, blank=True)
    name = models.CharField(max_length=255)
    url = models.URLField(max_length=500)
    timezone = models.CharField(max_length=64)
    lang = models.CharField(max_length=35, blank=True)
    phone = models.CharField(max_length=64, blank=True)
    fare_url = models.URLField(max_length=500, blank=True)
    email = models.EmailField(blank=True)
    # Each agency's own timetable version and validity, where a merged feed
    # says (511's regional feed: mtc_feed_versions.txt). A single-agency feed
    # has feed_info.txt for that instead.
    feed_version = models.CharField(max_length=64, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name_plural = "agencies"
        constraints = [
            models.UniqueConstraint(fields=["feed", "agency_id"], name="agency_unique_per_feed"),
            models.CheckConstraint(condition=~Q(name=""), name="agency_name_required"),
            models.CheckConstraint(condition=~Q(timezone=""), name="agency_timezone_required"),
            models.CheckConstraint(
                condition=Q(start_date__isnull=True)
                | Q(end_date__isnull=True)
                | Q(end_date__gte=F("start_date")),
                name="agency_date_range_valid",
            ),
        ]

    def __str__(self):
        return self.name


class Stop(models.Model):
    """stops.txt: platforms, stations, entrances, nodes and boarding areas."""

    feed = models.ForeignKey("Feed", on_delete=models.CASCADE, related_name="stops")
    stop_id = models.CharField(max_length=255)
    code = models.CharField(max_length=255, blank=True)
    name = models.CharField(max_length=255, blank=True)
    desc = models.TextField(blank=True)
    point = models.PointField(null=True, blank=True, srid=4326)
    zone_id = models.CharField(max_length=255, blank=True)
    url = models.URLField(max_length=500, blank=True)
    location_type = models.PositiveSmallIntegerField(
        choices=LocationType.choices, default=LocationType.STOP
    )
    parent_station = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE, related_name="children"
    )
    timezone = models.CharField(max_length=64, blank=True)
    wheelchair_boarding = models.PositiveSmallIntegerField(
        choices=Accessibility.choices, default=Accessibility.UNKNOWN
    )
    platform_code = models.CharField(max_length=64, blank=True)
    # Set by the importer for stops and stations; see transit.models.places.
    place = models.ForeignKey(
        "Place", null=True, blank=True, on_delete=models.SET_NULL, related_name="stops"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["feed", "stop_id"], name="stop_unique_per_feed"),
            models.CheckConstraint(
                condition=_in("location_type", LocationType), name="stop_location_type_valid"
            ),
            models.CheckConstraint(
                condition=_in("wheelchair_boarding", Accessibility),
                name="stop_wheelchair_boarding_valid",
            ),
            # Stops, stations and entrances are places a rider goes, so they
            # need a name and a location. Nodes and boarding areas may omit both.
            models.CheckConstraint(
                condition=Q(location_type__in=[3, 4]) | (~Q(name="") & Q(point__isnull=False)),
                name="stop_name_and_point_required",
            ),
            models.CheckConstraint(
                condition=~Q(location_type=LocationType.STATION) | Q(parent_station__isnull=True),
                name="station_has_no_parent",
            ),
            models.CheckConstraint(
                condition=~Q(location_type__in=[2, 3, 4]) | Q(parent_station__isnull=False),
                name="entrance_node_boarding_area_need_parent",
            ),
        ]
        indexes = [models.Index(fields=["feed", "location_type"])]

    def __str__(self):
        return f"{self.name or self.stop_id}"

    @property
    def lat(self):
        return self.point.y if self.point else None

    @property
    def lon(self):
        return self.point.x if self.point else None


class Route(models.Model):
    """routes.txt"""

    feed = models.ForeignKey("Feed", on_delete=models.CASCADE, related_name="routes")
    route_id = models.CharField(max_length=255)
    agency = models.ForeignKey(Agency, on_delete=models.CASCADE, related_name="routes")
    short_name = models.CharField(max_length=255, blank=True)
    long_name = models.CharField(max_length=255, blank=True)
    desc = models.TextField(blank=True)
    # Basic types 0-7, 11, 12, or Google's extended types 100-1799.
    route_type = models.PositiveSmallIntegerField()
    url = models.URLField(max_length=500, blank=True)
    color = models.CharField(max_length=6, blank=True)
    text_color = models.CharField(max_length=6, blank=True)
    sort_order = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["sort_order", "route_id"]
        constraints = [
            models.UniqueConstraint(fields=["feed", "route_id"], name="route_unique_per_feed"),
            models.CheckConstraint(
                condition=~Q(short_name="") | ~Q(long_name=""), name="route_needs_a_name"
            ),
            models.CheckConstraint(
                condition=Q(route_type__lte=7)
                | Q(route_type__in=[11, 12])
                | Q(route_type__gte=100, route_type__lte=1799),
                name="route_type_valid",
            ),
            models.CheckConstraint(condition=Q(color__regex=HEX_COLOR), name="route_color_hex"),
            models.CheckConstraint(
                condition=Q(text_color__regex=HEX_COLOR), name="route_text_color_hex"
            ),
        ]

    def __str__(self):
        return self.short_name or self.long_name


class Service(models.Model):
    """calendar.txt, plus services that only exist in calendar_dates.txt.

    A service defined only by exceptions has no weekly pattern: every weekday
    is False and both dates are null.
    """

    feed = models.ForeignKey("Feed", on_delete=models.CASCADE, related_name="services")
    service_id = models.CharField(max_length=255)
    monday = models.BooleanField(default=False)
    tuesday = models.BooleanField(default=False)
    wednesday = models.BooleanField(default=False)
    thursday = models.BooleanField(default=False)
    friday = models.BooleanField(default=False)
    saturday = models.BooleanField(default=False)
    sunday = models.BooleanField(default=False)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

    WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["feed", "service_id"], name="service_unique_per_feed"),
            models.CheckConstraint(
                condition=Q(start_date__isnull=True, end_date__isnull=True)
                | Q(start_date__isnull=False, end_date__gte=F("start_date")),
                name="service_date_range_valid",
            ),
        ]

    def __str__(self):
        return self.service_id


class ServiceDate(models.Model):
    """calendar_dates.txt"""

    feed = models.ForeignKey("Feed", on_delete=models.CASCADE, related_name="+")
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name="dates")
    date = models.DateField()
    exception_type = models.PositiveSmallIntegerField(choices=ExceptionType.choices)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["service", "date"], name="service_date_unique"),
            models.CheckConstraint(
                condition=_in("exception_type", ExceptionType), name="exception_type_valid"
            ),
        ]
        indexes = [models.Index(fields=["feed", "date"])]

    def __str__(self):
        return f"{self.service} {self.date} {self.get_exception_type_display()}"


class Shape(models.Model):
    """shapes.txt, folded into one line per shape_id at import."""

    feed = models.ForeignKey("Feed", on_delete=models.CASCADE, related_name="shapes")
    shape_id = models.CharField(max_length=255)
    geometry = models.LineStringField(srid=4326)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["feed", "shape_id"], name="shape_unique_per_feed"),
        ]

    def __str__(self):
        return self.shape_id


class Trip(models.Model):
    """trips.txt"""

    feed = models.ForeignKey("Feed", on_delete=models.CASCADE, related_name="trips")
    trip_id = models.CharField(max_length=255)
    route = models.ForeignKey(Route, on_delete=models.CASCADE, related_name="trips")
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name="trips")
    headsign = models.CharField(max_length=255, blank=True)
    short_name = models.CharField(max_length=255, blank=True)
    direction_id = models.PositiveSmallIntegerField(null=True, blank=True)
    block_id = models.CharField(max_length=255, blank=True)
    shape = models.ForeignKey(
        Shape, null=True, blank=True, on_delete=models.SET_NULL, related_name="trips"
    )
    wheelchair_accessible = models.PositiveSmallIntegerField(
        choices=Accessibility.choices, default=Accessibility.UNKNOWN
    )
    bikes_allowed = models.PositiveSmallIntegerField(
        choices=Accessibility.choices, default=Accessibility.UNKNOWN
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["feed", "trip_id"], name="trip_unique_per_feed"),
            models.CheckConstraint(
                condition=Q(direction_id__isnull=True) | Q(direction_id__in=[0, 1]),
                name="trip_direction_valid",
            ),
            models.CheckConstraint(
                condition=_in("wheelchair_accessible", Accessibility),
                name="trip_wheelchair_valid",
            ),
            models.CheckConstraint(
                condition=_in("bikes_allowed", Accessibility), name="trip_bikes_valid"
            ),
        ]

    def __str__(self):
        return self.short_name or self.trip_id


class StopTime(models.Model):
    """stop_times.txt

    Times are seconds after the start of the service day. Intermediate
    non-timepoint stops may leave both blank; the importer guarantees the
    first and last stop of every trip are timed and that times never go
    backwards along a trip.
    """

    feed = models.ForeignKey("Feed", on_delete=models.CASCADE, related_name="+")
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="stop_times")
    stop = models.ForeignKey(Stop, on_delete=models.CASCADE, related_name="stop_times")
    stop_sequence = models.PositiveIntegerField()
    arrival_secs = models.PositiveIntegerField(null=True, blank=True)
    departure_secs = models.PositiveIntegerField(null=True, blank=True)
    stop_headsign = models.CharField(max_length=255, blank=True)
    pickup_type = models.PositiveSmallIntegerField(
        choices=PickupDropOff.choices, default=PickupDropOff.REGULAR
    )
    drop_off_type = models.PositiveSmallIntegerField(
        choices=PickupDropOff.choices, default=PickupDropOff.REGULAR
    )
    shape_dist_traveled = models.FloatField(null=True, blank=True)
    timepoint = models.BooleanField(default=True)

    class Meta:
        ordering = ["trip", "stop_sequence"]
        constraints = [
            models.UniqueConstraint(fields=["trip", "stop_sequence"], name="stop_time_sequence"),
            models.CheckConstraint(
                condition=Q(arrival_secs__isnull=True, departure_secs__isnull=True)
                | Q(arrival_secs__isnull=False, departure_secs__gte=F("arrival_secs")),
                name="stop_time_departs_after_arriving",
            ),
            models.CheckConstraint(
                condition=_in("pickup_type", PickupDropOff), name="stop_time_pickup_valid"
            ),
            models.CheckConstraint(
                condition=_in("drop_off_type", PickupDropOff), name="stop_time_drop_off_valid"
            ),
            models.CheckConstraint(
                condition=Q(shape_dist_traveled__isnull=True) | Q(shape_dist_traveled__gte=0),
                name="stop_time_distance_non_negative",
            ),
        ]
        indexes = [
            # The planner's hot path: departures from a set of stops after a time.
            models.Index(fields=["stop", "departure_secs"]),
        ]

    def __str__(self):
        return f"{self.trip_id}#{self.stop_sequence}"


class FareAttribute(models.Model):
    """fare_attributes.txt"""

    feed = models.ForeignKey("Feed", on_delete=models.CASCADE, related_name="fares")
    fare_id = models.CharField(max_length=255)
    agency = models.ForeignKey(Agency, null=True, blank=True, on_delete=models.CASCADE)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    currency_type = models.CharField(max_length=3)
    payment_method = models.PositiveSmallIntegerField()
    transfers = models.PositiveSmallIntegerField(null=True, blank=True)
    transfer_duration = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["feed", "fare_id"], name="fare_unique_per_feed"),
            models.CheckConstraint(condition=Q(price__gte=0), name="fare_price_non_negative"),
            models.CheckConstraint(
                condition=Q(payment_method__in=[0, 1]), name="fare_payment_valid"
            ),
            models.CheckConstraint(
                condition=Q(transfers__isnull=True) | Q(transfers__in=[0, 1, 2]),
                name="fare_transfers_valid",
            ),
            models.CheckConstraint(
                condition=Q(currency_type__regex=r"^[A-Z]{3}$"), name="fare_currency_iso4217"
            ),
        ]

    def __str__(self):
        return f"{self.fare_id} {self.price} {self.currency_type}"


class FareRule(models.Model):
    """fare_rules.txt. Zones are plain ids; they have no table of their own in GTFS."""

    feed = models.ForeignKey("Feed", on_delete=models.CASCADE, related_name="+")
    fare = models.ForeignKey(FareAttribute, on_delete=models.CASCADE, related_name="rules")
    route = models.ForeignKey(Route, null=True, blank=True, on_delete=models.CASCADE)
    origin_id = models.CharField(max_length=255, blank=True)
    destination_id = models.CharField(max_length=255, blank=True)
    contains_id = models.CharField(max_length=255, blank=True)

    class Meta:
        indexes = [models.Index(fields=["feed", "origin_id", "destination_id"])]

    def __str__(self):
        return f"{self.fare_id}: {self.origin_id or '*'} -> {self.destination_id or '*'}"
