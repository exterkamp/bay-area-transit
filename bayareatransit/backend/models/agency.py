from django.db import models
from backend.models.base import Base

class Agency(Base):
    """One or more transit agencies that provide the data in this feed.

    Maps to agency.txt in the GTFS feed.
    """
    feed = models.ForeignKey('Feed', on_delete=models.CASCADE)
    agency_id = models.CharField(
        max_length=255, blank=True, db_index=True,
        help_text="Unique identifier for transit agency")
    name = models.CharField(
        max_length=255,
        help_text="Full name of the transit agency")
    url = models.URLField(
        blank=True, help_text="URL of the transit agency")
    timezone = models.CharField(
        max_length=255,
        help_text="Timezone of the agency")
    lang = models.CharField(
        max_length=2, blank=True,
        help_text="ISO 639-1 code for the primary language")
    phone = models.CharField(
        max_length=255, blank=True,
        help_text="Voice telephone number")
    fare_url = models.URLField(
        blank=True, help_text="URL for purchasing tickets online")
    extra_data = models.JSONField(blank=True, null=True)

    def __str__(self):
        return u"%d-%s" % (self.feed.id, self.agency_id)

    class Meta:
        verbose_name_plural = "agencies"

    # GTFS column names to fields, used by Base for import/export
    _column_map = (
        ('agency_id', 'agency_id'),
        ('agency_name', 'name'),
        ('agency_url', 'url'),
        ('agency_timezone', 'timezone'),
        ('agency_lang', 'lang'),
        ('agency_phone', 'phone'),
        ('agency_fare_url', 'fare_url')
    )
    _filename = 'agency.txt'
    _unique_fields = ('agency_id',)