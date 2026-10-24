from django.contrib.gis.db import models
from django.db.models import Q


class Operator(models.Model):
    """A 511.org operator, e.g. CT (Caltrain). Feeds and realtime hang off this."""

    code = models.CharField(max_length=16, unique=True)
    name = models.CharField(max_length=255)
    timezone = models.CharField(max_length=64, default="America/Los_Angeles")

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} {self.name}"

    @property
    def active_feed(self):
        return self.feeds.filter(is_active=True).first()


class Feed(models.Model):
    """One imported static GTFS feed for an operator.

    A feed is imported inside a single transaction and only becomes visible
    once it is complete, so readers never see a half-imported feed. At most
    one feed per operator is active; the API only ever reads the active one.
    """

    operator = models.ForeignKey(Operator, on_delete=models.CASCADE, related_name="feeds")
    sha256 = models.CharField(max_length=64, help_text="Hash of the source archive")
    is_active = models.BooleanField(default=False)
    version = models.CharField(max_length=255, blank=True)
    publisher_name = models.CharField(max_length=255, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    imported_at = models.DateTimeField(auto_now_add=True)
    stats = models.JSONField(default=dict, blank=True, help_text="Row counts and warnings")

    class Meta:
        ordering = ["operator", "-imported_at"]
        constraints = [
            models.UniqueConstraint(fields=["operator", "sha256"], name="feed_unique_archive"),
            models.UniqueConstraint(
                fields=["operator"],
                condition=Q(is_active=True),
                name="one_active_feed_per_operator",
            ),
            models.CheckConstraint(
                condition=Q(start_date__isnull=True)
                | Q(end_date__isnull=True)
                | Q(end_date__gte=models.F("start_date")),
                name="feed_date_range_valid",
            ),
        ]

    def __str__(self):
        state = "active" if self.is_active else "inactive"
        return f"{self.operator.code} {self.version or self.sha256[:8]} ({state})"
