from backend.models.trip import Trip
from backend.models.stop_time import StopTime
from rest_framework import serializers
from backend.serializers.stop_time import StopTimeSerializer


class TripSerializer(serializers.ModelSerializer):
    class Meta:
        model = Trip
        fields = '__all__'

class ToplevelTripSerializer(serializers.ModelSerializer):
    stops = StopTimeSerializer(many=True)

    class Meta:
        model = Trip
        fields = ['id', 'short_name', 'headsign', 'direction', 'service', 'stops']