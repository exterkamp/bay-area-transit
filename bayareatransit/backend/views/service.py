from backend.models.service import Service
from backend.serializers.service import ServiceSerializer
from rest_framework import viewsets
from rest_framework_extensions.mixins import NestedViewSetMixin


class ServiceViewSet(NestedViewSetMixin, viewsets.ModelViewSet):
    queryset = Service.objects.all()
    serializer_class = ServiceSerializer