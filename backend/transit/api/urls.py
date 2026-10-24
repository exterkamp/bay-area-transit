from django.urls import path

from . import views

urlpatterns = [
    path("operators", views.operators),
    path("operators/<str:code>/stations", views.stations),
    path("operators/<str:code>/stations/<str:station_id>/departures", views.departures),
    path("operators/<str:code>/routes", views.routes),
    path("operators/<str:code>/shapes", views.shapes),
    path("operators/<str:code>/plan", views.plan),
    path("operators/<str:code>/trips/<str:trip_id>", views.trip),
    path("operators/<str:code>/vehicles", views.vehicles),
    path("operators/<str:code>/alerts", views.alerts),
]
