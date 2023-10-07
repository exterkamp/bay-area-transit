from backend.models.agency import Agency
from rest_framework import serializers


class AgencySerializer(serializers.ModelSerializer):
    class Meta:
        model = Agency
        fields = '__all__'