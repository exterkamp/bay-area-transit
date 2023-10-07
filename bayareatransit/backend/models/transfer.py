from django.db import models
from backend.models.base import Base


class Transfer(Base):
    """Create additional rules for transfers between ambiguous stops.

    Implements transfer.txt in the GTFS feed.
    """
    from_stop = models.ForeignKey(
        'Stop', on_delete=models.CASCADE,
        related_name='transfer_from_stop',
        help_text='Stop where a connection between routes begins.')
    to_stop = models.ForeignKey(
        'Stop', on_delete=models.CASCADE,
        related_name='transfer_to_stop',
        help_text='Stop where a connection between routes ends.')
    transfer_type = models.IntegerField(
        default=0, blank=True,
        choices=((0, 'Recommended transfer point'),
                 (1, 'Timed transfer point (vehicle will wait)'),
                 (2, 'min_transfer_time needed to successfully transfer'),
                 (3, 'No transfers possible')),
        help_text="What kind of transfer?")
    min_transfer_time = models.IntegerField(
        null=True, blank=True,
        help_text="How many seconds are required to transfer?")
    extra_data = models.JSONField(default=dict, blank=True, null=True)

    def __str__(self):
        return "%s-%s" % (self.from_stop, self.to_stop.stop_id)

    _column_map = (
        ('from_stop_id', 'from_stop__stop_id'),
        ('to_stop_id', 'to_stop__stop_id'),
        ('transfer_type', 'transfer_type'),
        ('min_transfer_time', 'min_transfer_time')
    )
    _filename = 'transfers.txt'
    _rel_to_feed = 'from_stop__feed'
    _sort_order = ('from_stop__stop_id', 'to_stop__stop_id')
    _unique_fields = ('from_stop_id', 'to_stop_id')