from backend.models.stop import Stop
from rest_framework import serializers


class StopSerializer(serializers.ModelSerializer):
    class Meta:
        model = Stop
        fields = '__all__'