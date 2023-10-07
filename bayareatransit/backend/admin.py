from django.contrib import admin

from .models.feed import Feed
from .models.feed_info import FeedInfo
from .models.agency import Agency
from .models.route import Route
from .models.stop import Stop
from .models.zone import Zone

# Register your models here.
admin.site.register(Feed)
admin.site.register(FeedInfo)
admin.site.register(Agency)
admin.site.register(Route)
admin.site.register(Stop)
admin.site.register(Zone)