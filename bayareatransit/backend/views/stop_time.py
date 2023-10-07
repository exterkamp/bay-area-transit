from backend.models.stop_time import StopTime
from backend.serializers.stop_time import StopTimeSerializer
from rest_framework import viewsets
from rest_framework_extensions.mixins import NestedViewSetMixin


class StopTimeViewSet(NestedViewSetMixin, viewsets.ModelViewSet):
    queryset = StopTime.objects.all()
    serializer_class = StopTimeSerializer