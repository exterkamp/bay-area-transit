"""GTFS-realtime snapshots.

Realtime is not history: each poll replaces the previous snapshot for that
operator and feed kind in one transaction. Records reference static trips and
stops by their GTFS ids rather than foreign keys, because realtime routinely
mentions trips the static feed doesn't have (added trips, a newer schedule),
and a static feed swap must not cascade-delete realtime or vice versa.
"""

from django.contrib.gis.db import models
from django.db.models import Q

from .feed import Operator


class RealtimeKind(models.TextChoices):
    TRIP_UPDATES = "trip_updates", "Trip updates"
    VEHICLE_POSITIONS = "vehicle_positions", "Vehicle positions"
    ALERTS = "alerts", "Service alerts"


class TripRelationship(models.IntegerChoices):
    # Values from GTFS-realtime TripDescriptor.ScheduleRelationship.
    SCHEDULED = 0, "Scheduled"
    ADDED = 1, "Added"
    UNSCHEDULED = 2, "Unscheduled"
    CANCELED = 3, "Canceled"
    REPLACEMENT = 5, "Replacement"
    DUPLICATED = 6, "Duplicated"
    DELETED = 7, "Deleted"


class StopRelationship(models.IntegerChoices):
    # Values from GTFS-realtime StopTimeUpdate.ScheduleRelationship.
    SCHEDULED = 0, "Scheduled"
    SKIPPED = 1, "Skipped"
    NO_DATA = 2, "No data"
    UNSCHEDULED = 3, "Unscheduled"


class VehicleStatus(models.IntegerChoices):
    INCOMING_AT = 0, "Incoming at"
    STOPPED_AT = 1, "Stopped at"
    IN_TRANSIT_TO = 2, "In transit to"


class RealtimeFetch(models.Model):
    """The outcome of the most recent poll of one realtime feed."""

    operator = models.ForeignKey(Operator, on_delete=models.CASCADE, related_name="+")
    kind = models.CharField(max_length=32, choices=RealtimeKind.choices)
    fetched_at = models.DateTimeField(null=True, blank=True, help_text="Last successful poll")
    feed_timestamp = models.DateTimeField(null=True, blank=True, help_text="Header timestamp")
    entity_count = models.PositiveIntegerField(default=0)
    attempted_at = models.DateTimeField()
    error = models.TextField(blank=True, help_text="Why the last attempt failed, if it did")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["operator", "kind"], name="one_fetch_row_per_feed"),
        ]

    def __str__(self):
        return f"{self.operator.code} {self.kind} @ {self.fetched_at}"


class TripUpdate(models.Model):
    operator = models.ForeignKey(Operator, on_delete=models.CASCADE, related_name="+")
    trip_id = models.CharField(max_length=255)
    start_date = models.DateField(null=True, blank=True)
    schedule_relationship = models.PositiveSmallIntegerField(
        choices=TripRelationship.choices, default=TripRelationship.SCHEDULED
    )
    vehicle_id = models.CharField(max_length=255, blank=True)
    delay = models.IntegerField(null=True, blank=True, help_text="Trip-level delay, seconds")
    timestamp = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["operator", "trip_id"])]

    def __str__(self):
        return f"{self.operator.code} trip {self.trip_id}"


class StopTimeUpdate(models.Model):
    trip_update = models.ForeignKey(
        TripUpdate, on_delete=models.CASCADE, related_name="stop_time_updates"
    )
    stop_sequence = models.PositiveIntegerField(null=True, blank=True)
    stop_id = models.CharField(max_length=255, blank=True)
    arrival_delay = models.IntegerField(null=True, blank=True)
    arrival_time = models.DateTimeField(null=True, blank=True)
    departure_delay = models.IntegerField(null=True, blank=True)
    departure_time = models.DateTimeField(null=True, blank=True)
    schedule_relationship = models.PositiveSmallIntegerField(
        choices=StopRelationship.choices, default=StopRelationship.SCHEDULED
    )

    class Meta:
        constraints = [
            # GTFS-rt requires at least one of the two to identify the stop.
            models.CheckConstraint(
                condition=Q(stop_sequence__isnull=False) | ~Q(stop_id=""),
                name="stop_time_update_identifies_stop",
            ),
        ]

    def __str__(self):
        return f"{self.trip_update.trip_id}@{self.stop_sequence or self.stop_id}"


class VehiclePosition(models.Model):
    operator = models.ForeignKey(Operator, on_delete=models.CASCADE, related_name="+")
    vehicle_id = models.CharField(max_length=255, blank=True)
    label = models.CharField(max_length=255, blank=True)
    trip_id = models.CharField(max_length=255, blank=True)
    start_date = models.DateField(null=True, blank=True)
    point = models.PointField(srid=4326)
    bearing = models.FloatField(null=True, blank=True)
    speed = models.FloatField(null=True, blank=True, help_text="Meters per second")
    current_status = models.PositiveSmallIntegerField(
        choices=VehicleStatus.choices, null=True, blank=True
    )
    stop_id = models.CharField(max_length=255, blank=True)
    current_stop_sequence = models.PositiveIntegerField(null=True, blank=True)
    timestamp = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["operator", "trip_id"])]
        constraints = [
            models.CheckConstraint(
                condition=Q(bearing__isnull=True) | Q(bearing__gte=0, bearing__lt=360),
                name="vehicle_bearing_valid",
            ),
        ]

    def __str__(self):
        return f"{self.operator.code} vehicle {self.vehicle_id or self.label}"


class Alert(models.Model):
    operator = models.ForeignKey(Operator, on_delete=models.CASCADE, related_name="+")
    alert_id = models.CharField(max_length=255)
    header = models.TextField(blank=True)
    description = models.TextField(blank=True)
    url = models.TextField(blank=True)
    cause = models.CharField(max_length=64, blank=True)
    effect = models.CharField(max_length=64, blank=True)
    # [[start_epoch|null, end_epoch|null], ...]; empty means always active.
    active_periods = models.JSONField(default=list, blank=True)
    # The agencies it's about, worked out when polled: named by an informed
    # entity, or behind its routes and stops (see realtime.poller).
    agencies = models.JSONField(default=list, blank=True)
    route_ids = models.JSONField(default=list, blank=True)
    stop_ids = models.JSONField(default=list, blank=True)
    trip_ids = models.JSONField(default=list, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["operator", "alert_id"], name="alert_unique"),
        ]

    def __str__(self):
        return self.header or self.alert_id
