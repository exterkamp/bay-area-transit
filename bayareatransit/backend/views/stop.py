from backend.models.stop import Stop
from backend.serializers.stop import StopSerializer
from rest_framework import viewsets
from rest_framework_extensions.mixins import NestedViewSetMixin


class StopViewSet(NestedViewSetMixin, viewsets.ModelViewSet):
    queryset = Stop.objects.all()
    serializer_class = StopSerializer