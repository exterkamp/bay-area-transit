from backend.models.route import Route
from rest_framework import serializers


class RouteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Route
        fields = '__all__'