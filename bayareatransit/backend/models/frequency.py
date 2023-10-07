from django.db import models
from backend.models.base import Base
from datetime import timedelta


class Frequency(Base):
    """Description of a trip that repeats without fixed stop times"""
    trip = models.ForeignKey('Trip', on_delete=models.CASCADE)
    start_time = models.DurationField(default=timedelta, 
        help_text="Time that the service begins at the specified frequency")
    end_time = models.DurationField(default=timedelta, 
        help_text="Time that the service ends at the specified frequency")
    headway_secs = models.IntegerField(
        help_text="Time in seconds before returning to same stop")
    exact_times = models.CharField(
        max_length=1, blank=True,
        choices=(('0', 'Trips are not exactly scheduled'),
                 ('1', 'Trips are exactly scheduled from start time')),
        help_text="Should frequency-based trips be exactly scheduled?")
    extra_data = models.JSONField(default=dict, blank=True, null=True)

    def __str__(self):
        return str(self.trip)

    class Meta:
        verbose_name_plural = "frequencies"

    # For Base import/export
    _column_map = (
        ('trip_id', 'trip__trip_id'),
        ('start_time', 'start_time'),
        ('end_time', 'end_time'),
        ('headway_secs', 'headway_secs'),
        ('exact_times', 'exact_times'))
    _filename = 'frequencies.txt'
    _rel_to_feed = 'trip__route__feed'
    _unique_fields = ('trip_id', 'start_time')