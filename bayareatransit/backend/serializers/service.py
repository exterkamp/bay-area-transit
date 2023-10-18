from backend.models.service import Service
from backend.models.service_date import ServiceDate
from rest_framework import serializers

class ServiceDateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceDate
        fields = ['date', 'exception_type']

class ServiceSerializer(serializers.ModelSerializer):
    dates = ServiceDateSerializer(many=True)

    class Meta:
        model = Service
        fields = '__all__'