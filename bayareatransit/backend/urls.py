from django.urls import path

from django.urls import include, path
from rest_framework import routers
from .views.user import UserViewSet
from .views.feed import FeedViewSet, FeedInfoViewSet
from .views.agency import AgencyViewSet
from .views.route import RouteViewSet
from .views.trip import TripViewSet
from .views.stop import StopViewSet
from .views.service import ServiceViewSet
from .views.stop_time import StopTimeViewSet
from .views.healthcheck import healthcheck
from rest_framework_extensions.routers import ExtendedSimpleRouter

router = ExtendedSimpleRouter()
(
    router.register(r'users', UserViewSet, basename='user')
)

feeds_routes = router.register(
    r'api/v1/feeds',
    FeedViewSet,
    basename='feeds'
)
feeds_routes.register(
    r'info',
    FeedInfoViewSet,
    basename='feeds-info',
    parents_query_lookups=['feed']
)
feeds_routes.register(
    r'stops',
    StopViewSet,
    basename='stops',
    parents_query_lookups=['feed']
)
feeds_routes.register(
    r'trips',
    TripViewSet,
    basename='trips',
    parents_query_lookups=['route__feed']
)
feeds_routes.register(
    r'services',
    ServiceViewSet,
    basename='service',
    parents_query_lookups=['feed']
)

(
    feeds_routes.register(r'agencies',
                          AgencyViewSet,
                          basename='agencies',
                          parents_query_lookups=['feed'])
                .register(r'routes',
                          RouteViewSet,
                          basename='routes',
                          parents_query_lookups=['feed', 'agency'])
                .register(r'trips',
                          TripViewSet,
                          basename='trips',
                          parents_query_lookups=['route__feed', 'route__agency', 'route'])
                .register(r'stops',
                          StopTimeViewSet,
                          basename='stops',
                          parents_query_lookups=['trip__route__feed', 'trip__route__agency', 'trip__route', 'trip'])
)

urlpatterns = [
    path("healthz", healthcheck, name="healthz"),
] + router.urls
