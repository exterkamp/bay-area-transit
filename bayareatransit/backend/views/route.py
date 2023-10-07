from backend.models.route import Route
from backend.models.agency import Agency
from backend.serializers.route import RouteSerializer
from rest_framework import viewsets
from rest_framework_extensions.mixins import NestedViewSetMixin


class RouteViewSet(NestedViewSetMixin, viewsets.ModelViewSet):
    queryset = Route.objects.all()
    serializer_class = RouteSerializer
