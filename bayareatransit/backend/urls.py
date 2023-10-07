from django.urls import path

# from . import views

from django.urls import include, path
from rest_framework import routers
from .views.user import UserViewSet
from .views.feed import FeedViewSet, FeedInfoViewSet
from .views.agency import AgencyViewSet
from .views.route import RouteViewSet
from .views.trip import TripViewSet
from rest_framework_extensions.routers import ExtendedSimpleRouter

router = ExtendedSimpleRouter()
(
    router.register(r'users', UserViewSet, basename='user')
)
# (
#     router.register(r'feeds', FeedViewSet, basename='feeds')
#           .register(r'info', FeedInfoViewSet, 
#                     basename='feeds-feeds_info',
#                     parents_query_lookups=['feed'])
# )

feeds_routes = router.register(
    r'feeds',
    FeedViewSet,
    basename='feeds'
)
feeds_routes.register(
    r'info',
    FeedInfoViewSet,
    basename='feeds-info',
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
)

# (
#     router.register(r'agencies', AgencyViewSet, basename='agencies')
#           .register(r'routes', RouteViewSet, basename='routes',
#                     parents_query_lookups=['agency__agency_id'])
#           .register(r'trips', TripViewSet, basename='trips',
#                     parents_query_lookups=['route__agency__agency_id', 'route'])
# )
    #   .register(r'permissions',
    #             PermissionViewSet,
    #             basename='users-groups-permission',
    #             parents_query_lookups=['group__user', 'group'])

urlpatterns = router.urls

# path('api/', include('izzi.api.urls')) # removed namespace


# router = routers.DefaultRouter()
# router.register(r'users', UserViewSet)
# router.register(r'feeds', FeedViewSet)
# router.register(r'feeds/info', FeedInfoViewSet)

# urlpatterns = [
#     path('', include(router.urls)),
#     # path("", views.index, name="index"),
# ]