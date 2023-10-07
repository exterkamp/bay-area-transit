from backend.models.agency import Agency
from backend.serializers.agency import AgencySerializer
from rest_framework import viewsets
from rest_framework_extensions.mixins import NestedViewSetMixin
from django.db.models import Max, F


class AgencyViewSet(NestedViewSetMixin, viewsets.ModelViewSet):
    # lookup_field = "agency_id"
    queryset = Agency.objects.all()
    serializer_class = AgencySerializer

    # def get_queryset(self):
    #     agencies = Agency.objects.all()
    #     latest_agencies = {}

    #     for agency in agencies:
    #         if agency.agency_id not in latest_agencies:
    #             latest_agencies[agency.agency_id] = {
    #                 "created": agency.feed.created,
    #                 "dbid": agency.id,
    #             }
    #             continue
    #         # otherwise we need to check if we're newer.
    #         a = latest_agencies[agency.agency_id]
    #         if a["created"] < agency.feed.created:
    #             latest_agencies[agency.agency_id] = {
    #                 "created": agency.feed.created,
    #                 "dbid": agency.id,
    #             }

    #     ids = [a["dbid"] for a in latest_agencies.values()]

    #     return Agency.objects.filter(id__in=ids)

