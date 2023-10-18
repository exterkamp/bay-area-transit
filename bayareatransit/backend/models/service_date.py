from django.db import models
from backend.models.base import Base


class ServiceDate(Base):
    """Dates that a route is active.

    Implements calendar_dates.txt
    """
    service = models.ForeignKey('Service', related_name="dates", on_delete=models.CASCADE)
    date = models.DateField(
        help_text="Date that the service differs from the norm.")
    exception_type = models.IntegerField(
        default=1, choices=((1, 'Added'), (2, 'Removed')),
        help_text="Is service added or removed on this date?")
    extra_data = models.JSONField(default=dict, blank=True, null=True)

    def __str__(self):
        return (
            "%d-%s %s %s" % (
                self.service.feed.id, self.service.service_id, self.date,
                'Added' if self.exception_type == 1 else 'Removed'))

    # For Base import/export
    _column_map = (
        ('service_id', 'service__service_id'),
        ('date', 'date'),
        ('exception_type', 'exception_type'))
    _filename = 'calendar_dates.txt'
    _rel_to_feed = 'service__feed'
    _sort_order = ('date', 'exception_type')
    _unique_fields = ('service_id', 'date')