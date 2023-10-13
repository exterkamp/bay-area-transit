from django.contrib import admin

from .models.feed import Feed
from .models.feed_info import FeedInfo
from .models.agency import Agency
from .models.route import Route
from .models.stop import Stop
from .models.stop_time import StopTime
from .models.zone import Zone
from .models.service import Service
from .models.service_date import ServiceDate
from .models.trip import Trip, Block
from .models.frequency import Frequency
from .models.fare import Fare, FareRule
from .models.transfer import Transfer
from .models.shape import Shape, ShapePoint

# Register your models here.
admin.site.register(Feed)
admin.site.register(FeedInfo)
admin.site.register(Agency)
admin.site.register(Route)
admin.site.register(Stop)
admin.site.register(StopTime)
admin.site.register(Zone)
admin.site.register(Service)
admin.site.register(ServiceDate)
admin.site.register(Trip)
admin.site.register(Block)
admin.site.register(Frequency)
admin.site.register(Fare)
admin.site.register(FareRule)
admin.site.register(Transfer)
admin.site.register(ShapePoint)
admin.site.register(Shape)