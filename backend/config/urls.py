from django.contrib import admin
from django.urls import include, path

from transit.api.views import healthz

urlpatterns = [
    path("healthz", healthz, name="healthz"),
    path("api/v1/", include("transit.api.urls")),
    path("admin/", admin.site.urls),
]
