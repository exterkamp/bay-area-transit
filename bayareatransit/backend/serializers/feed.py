from backend.models.feed import Feed
from backend.models.feed_info import FeedInfo
from rest_framework import serializers
from rest_framework_extensions.fields import ResourceUriField


class FeedSerializer(serializers.ModelSerializer):
    class Meta:
        model = Feed
        fields = '__all__'


class FeedInfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeedInfo
        fields = '__all__'