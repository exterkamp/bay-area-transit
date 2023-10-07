from django.db import models
from backend.models.base import Base


class Zone(Base):
    """Represents a fare zone.

    This data is not represented as a file in the GTFS.  It appears as an
    identifier in the fare_rules and the stop tables.
    """
    feed = models.ForeignKey('Feed', on_delete=models.CASCADE)
    zone_id = models.CharField(
        max_length=63, db_index=True,
        help_text="Unique identifier for a zone.")

    def __str__(self):
        return "%d-%s" % (self.feed_id, self.zone_id)
