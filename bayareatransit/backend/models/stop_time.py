from django.db import models
from backend.models.base import Base
from datetime import timedelta

class StopTime(Base):
    """A specific stop on a route on a trip.

    This implements stop_times.txt in the GTFS feed
    """
    trip = models.ForeignKey('Trip', on_delete=models.CASCADE)
    stop = models.ForeignKey('Stop', on_delete=models.CASCADE)
    arrival_time = models.DurationField(
        default=timedelta, null=True, blank=True,
        help_text="Arrival time. Must be set for end stops of trip.")
    departure_time = models.DurationField(
        default=timedelta, null=True, blank=True,
        help_text='Departure time. Must be set for end stops of trip.')
    stop_sequence = models.IntegerField()
    stop_headsign = models.CharField(
        max_length=255, blank=True,
        help_text="Sign text that identifies the stop for passengers")
    pickup_type = models.CharField(
        max_length=1, blank=True,
        choices=(('0', 'Regularly scheduled pickup'),
                 ('1', 'No pickup available'),
                 ('2', 'Must phone agency to arrange pickup'),
                 ('3', 'Must coordinate with driver to arrange pickup')),
        help_text="How passengers are picked up")
    drop_off_type = models.CharField(
        max_length=1, blank=True,
        choices=(('0', 'Regularly scheduled drop off'),
                 ('1', 'No drop off available'),
                 ('2', 'Must phone agency to arrange drop off'),
                 ('3', 'Must coordinate with driver to arrange drop off')),
        help_text="How passengers are picked up")
    shape_dist_traveled = models.FloatField(
        "shape distance traveled",
        null=True, blank=True,
        help_text='Distance of stop from start of shape')
    extra_data = models.JSONField(default=dict, blank=True, null=True)

    def __str__(self):
        return "%s-%s-%s" % (self.trip, self.stop.stop_id, self.stop_sequence)

    _column_map = (
        ('trip_id', 'trip__trip_id'),
        ('arrival_time', 'arrival_time'),
        ('departure_time', 'departure_time'),
        ('stop_id', 'stop__stop_id'),
        ('stop_sequence', 'stop_sequence'),
        ('stop_headsign', 'stop_headsign'),
        ('pickup_type', 'pickup_type'),
        ('drop_off_type', 'drop_off_type'),
        ('shape_dist_traveled', 'shape_dist_traveled')
    )
    _filename = 'stop_times.txt'
    _rel_to_feed = 'trip__route__feed'
    _sort_order = ('trip__trip_id', 'stop_sequence')
    _unique_fields = ('trip_id', 'stop_sequence')