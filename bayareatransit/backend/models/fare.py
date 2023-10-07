from django.db import models
from backend.models.base import Base


class Fare(Base):
    """A fare class"""

    feed = models.ForeignKey('Feed', on_delete=models.CASCADE)
    fare_id = models.CharField(
        max_length=255, db_index=True,
        help_text="Unique identifier for a fare class")
    price = models.DecimalField(
        max_digits=17, decimal_places=4,
        help_text="Fare price, in units specified by currency_type")
    currency_type = models.CharField(
        max_length=3,
        help_text="ISO 4217 alphabetical currency code")
    payment_method = models.IntegerField(
        default=1,
        choices=((0, 'Fare is paid on board.'),
                 (1, 'Fare must be paid before boarding.')),
        help_text="When is the fare paid?")
    transfers = models.IntegerField(
        default=None, null=True, blank=True,
        choices=((0, 'No transfers permitted on this fare.'),
                 (1, 'Passenger may transfer once.'),
                 (2, 'Passenger may transfer twice.'),
                 (None, 'Unlimited transfers are permitted.')),
        help_text="Are transfers permitted?")
    transfer_duration = models.IntegerField(
        null=True, blank=True,
        help_text="Time in seconds until a ticket or transfer expires")
    extra_data = models.JSONField(default=dict, blank=True,  null=True)

    def __str__(self):
        return u"%d-%s(%s %s)" % (
            self.feed.id, self.fare_id, self.price, self.currency_type)

    # For Base import/export
    _column_map = (
        ('fare_id', 'fare_id'),
        ('price', 'price'),
        ('currency_type', 'currency_type'),
        ('payment_method', 'payment_method'),
        ('transfers', 'transfers'),
        ('transfer_duration', 'transfer_duration')
    )
    _filename = 'fare_attributes.txt'
    _unique_fields = ('fare_id',)


class FareRule(Base):
    """Associate a Fare with a Route and/or Zones"""
    fare = models.ForeignKey('Fare', on_delete=models.CASCADE)
    route = models.ForeignKey(
        'Route', null=True, blank=True, on_delete=models.SET_NULL,
        help_text="Fare class is valid for this route.")
    origin = models.ForeignKey(
        'Zone', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='fare_origins',
        help_text="Fare class is valid for travel originating in this zone.")
    destination = models.ForeignKey(
        'Zone', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='fare_destinations',
        help_text="Fare class is valid for travel ending in this zone.")
    contains = models.ForeignKey(
        'Zone', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='fare_contains',
        help_text="Fare class is valid for travel withing this zone.")
    extra_data = models.JSONField(default=dict, blank=True, null=True)

    def __str__(self):
        u = "%d-%s" % (self.fare.feed.id, self.fare.fare_id)
        if self.route:
            u += '-%s' % self.route.route_id
        return u

    # For Base import/export
    _column_map = (
        ('fare_id', 'fare__fare_id'),
        ('route_id', 'route__route_id'),
        ('origin_id', 'origin__zone_id'),
        ('destination_id', 'destination__zone_id'),
        ('contains_id', 'contains__zone_id')
    )
    _filename = 'fare_rules.txt'
    _rel_to_feed = 'fare__feed'
    _sort_order = ('route__route_id', 'fare__fare_id')
    _unique_fields = (
        'fare_id', 'route_id', 'origin_id', 'destination_id', 'contains_id')