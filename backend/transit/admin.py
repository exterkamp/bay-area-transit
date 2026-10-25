"""Admin is for looking, not editing: feeds are only ever written by the importer."""

from django.contrib import admin

from transit import models


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(models.Operator)
class OperatorAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "timezone"]


@admin.register(models.Feed)
class FeedAdmin(ReadOnlyAdmin):
    list_display = ["operator", "version", "is_active", "start_date", "end_date", "imported_at"]
    list_filter = ["operator", "is_active"]
    readonly_fields = ["stats"]


@admin.register(models.Stop)
class StopAdmin(ReadOnlyAdmin):
    list_display = ["stop_id", "name", "location_type", "parent_station", "feed"]
    list_filter = ["feed", "location_type"]
    search_fields = ["stop_id", "name"]


@admin.register(models.Route)
class RouteAdmin(ReadOnlyAdmin):
    list_display = ["route_id", "short_name", "long_name", "route_type", "feed"]
    list_filter = ["feed"]


@admin.register(models.Trip)
class TripAdmin(ReadOnlyAdmin):
    list_display = ["trip_id", "short_name", "route", "service", "headsign", "direction_id"]
    list_filter = ["feed", "route"]
    search_fields = ["trip_id", "short_name"]


@admin.register(models.RealtimeFetch)
class RealtimeFetchAdmin(ReadOnlyAdmin):
    list_display = ["operator", "kind", "fetched_at", "entity_count", "attempted_at", "error"]


@admin.register(models.Alert)
class AlertAdmin(ReadOnlyAdmin):
    list_display = ["alert_id", "operator", "header", "effect"]
