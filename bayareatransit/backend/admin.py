from django.contrib import admin

from .models.feed import Feed
from .models.feed_info import FeedInfo

# Register your models here.
admin.site.register(Feed)
admin.site.register(FeedInfo)