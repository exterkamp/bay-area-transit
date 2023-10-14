from backend.models.trip import Trip
from backend.serializers.trip import TripSerializer, ToplevelTripSerializer
from rest_framework import viewsets
from rest_framework_extensions.mixins import NestedViewSetMixin


class TripViewSet(NestedViewSetMixin, viewsets.ModelViewSet):
    queryset = Trip.objects.all()
    serializer_class = TripSerializer

    # def get_queryset(self):
    #     routes = Route.objects.all()
    #     agency_id = self.kwargs["parent_lookup_agency__agency_id"]

    #     a = Agency.objects.filter(agency_id=agency_id).latest('feed__created')

    #     return Route.objects.filter(feed=a.feed)

class ToplevelTripViewSet(NestedViewSetMixin, viewsets.ModelViewSet):
    queryset = Trip.objects.all()
    serializer_class = ToplevelTripSerializer