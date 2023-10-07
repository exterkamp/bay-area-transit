from backend.models.stop_time import StopTime
from rest_framework import serializers


class StopTimeSerializer(serializers.ModelSerializer):
    class Meta:
        model = StopTime
        fields = '__all__'