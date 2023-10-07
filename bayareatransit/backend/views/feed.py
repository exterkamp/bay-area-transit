from backend.models.feed import Feed
from backend.models.feed_info import FeedInfo
from backend.serializers.feed import FeedSerializer, FeedInfoSerializer
from rest_framework import generics
from rest_framework import viewsets
from rest_framework_extensions.mixins import NestedViewSetMixin


class FeedViewSet(NestedViewSetMixin, viewsets.ModelViewSet):
    queryset = Feed.objects.all()
    serializer_class = FeedSerializer

class FeedInfoViewSet(NestedViewSetMixin, viewsets.ModelViewSet):
    queryset = FeedInfo.objects.all()
    serializer_class = FeedInfoSerializer