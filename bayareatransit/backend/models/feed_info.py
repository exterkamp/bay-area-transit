from django.db import models
from backend.models.base import Base

class FeedInfo(Base):
    """Information about the feed

    Implements feed_info.txt in the GTFS feed.
    """
    feed = models.OneToOneField('Feed', on_delete=models.CASCADE)
    publisher_name = models.CharField(
        max_length=255,
        help_text="Full name of organization that publishes the feed.")
    publisher_url = models.URLField(
        help_text="URL of the feed publisher's organization.")
    lang = models.CharField(
        "language",
        max_length=20,
        help_text="IETF BCP 47 language code for text in field.")
    start_date = models.DateField(
        null=True, blank=True,
        help_text="Date that feed starts providing reliable data.")
    end_date = models.DateField(
        null=True, blank=True,
        help_text="Date that feed stops providing reliable data.")
    version = models.CharField(
        max_length=255, blank=True,
        help_text="Version of feed.")
    extra_data = models.JSONField(blank=True, null=True)

    def __str__(self):
        return '%s-%s' % (self.feed.id, self.publisher_name)

    _filename = 'feed_info.txt'
    _column_map = (
        ('feed_publisher_name', 'publisher_name'),
        ('feed_publisher_url', 'publisher_url'),
        ('feed_lang', 'lang'),
        ('feed_start_date', 'start_date'),
        ('feed_end_date', 'end_date'),
        ('feed_version', 'version')
    )
    _unique_fields = ('feed_publisher_name',)