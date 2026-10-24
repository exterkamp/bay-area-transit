import time
from datetime import UTC, date, datetime

from django.db import connection
from django.http import JsonResponse
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from transit import queries
from transit.models import Agency, Alert, Operator, RealtimeFetch, RealtimeKind, Route, Shape, Trip
from transit.queries import BadRequest, NotFound, context_for, hex_color, iso


def healthz(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    return JsonResponse({"status": "ok"})


def handles_errors(view):
    def wrapped(request, *args, **kwargs):
        try:
            return view(request, *args, **kwargs)
        except NotFound as exc:
            return Response({"detail": str(exc), "code": exc.code}, status=404)
        except BadRequest as exc:
            return Response({"detail": str(exc), "code": exc.code}, status=400)

    wrapped.__name__ = view.__name__
    wrapped.__doc__ = view.__doc__
    return wrapped


def parse_at(request, ctx) -> datetime:
    value = request.query_params.get("at")
    if not value:
        return timezone.now()
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        raise BadRequest("at must be an ISO 8601 datetime") from None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=ctx.tz)
    return moment.astimezone(UTC)


def parse_date(request, ctx) -> date:
    value = request.query_params.get("date")
    if not value:
        return timezone.now().astimezone(ctx.tz).date()
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise BadRequest("date must be YYYY-MM-DD") from None


@api_view(["GET"])
def operators(request):
    fetches = {}
    for fetch in RealtimeFetch.objects.all():
        fetches[(fetch.operator_id, fetch.kind)] = fetch.fetched_at
    agencies = {}
    for feed_pk, agency_id in Agency.objects.filter(feed__is_active=True).values_list(
        "feed_id", "agency_id"
    ):
        agencies.setdefault(feed_pk, []).append(agency_id)
    result = []
    for op in Operator.objects.all():
        tz = queries.ZoneInfo(op.timezone)
        feed = op.active_feed
        result.append(
            {
                "code": op.code,
                "name": op.name,
                "timezone": op.timezone,
                "feed": feed
                and {
                    "version": feed.version,
                    "start_date": feed.start_date and feed.start_date.isoformat(),
                    "end_date": feed.end_date and feed.end_date.isoformat(),
                    "imported_at": iso(feed.imported_at, tz),
                },
                "realtime": {
                    f"{kind}_at": iso(fetches.get((op.pk, kind)), tz)
                    for kind in RealtimeKind.values
                },
                "agencies": sorted(agencies.get(feed.pk, [])) if feed else [],
            }
        )
    return Response(result)


@api_view(["GET"])
@handles_errors
def agencies(request, code):
    return Response(queries.agencies(context_for(code)))


@api_view(["GET"])
@handles_errors
def places(request, code):
    params = request.query_params
    return Response(
        queries.search_places(
            context_for(code),
            q=params.get("q"),
            near=params.get("near"),
            radius=params.get("radius"),
            agency=params.get("agency"),
            limit=params.get("limit"),
        )
    )


@api_view(["GET"])
@handles_errors
def place(request, code, place_id):
    ctx = context_for(code)
    return Response(queries.place_dicts([queries.find_place(ctx, place_id)])[0])


@api_view(["GET"])
@handles_errors
def stations(request, code):
    params = request.query_params
    return Response(
        queries.stations(context_for(code), agency=params.get("agency"), route=params.get("route"))
    )


@api_view(["GET"])
@handles_errors
def routes(request, code):
    ctx = context_for(code)
    routes = Route.objects.filter(feed=ctx.feed).select_related("agency")
    if agency := request.query_params.get("agency"):
        routes = routes.filter(agency__agency_id__in=queries.agency_ids(agency))
    return Response(
        [
            {
                "id": r.route_id,
                "short_name": r.short_name,
                "long_name": r.long_name,
                "type": r.route_type,
                "color": hex_color(r.color, "#888888"),
                "text_color": hex_color(r.text_color, "#000000"),
                "agency": r.agency.agency_id,
            }
            for r in routes
        ]
    )


@api_view(["GET"])
@handles_errors
def shapes(request, code):
    ctx = context_for(code)
    trips = Trip.objects.filter(feed=ctx.feed, shape__isnull=False)
    if agency := request.query_params.get("agency"):
        trips = trips.filter(route__agency__agency_id__in=queries.agency_ids(agency))
    if route := request.query_params.get("route"):
        trips = trips.filter(route__route_id=route)
    route_of_shape = {}
    for shape_id, route_id, route_color, agency_id in trips.order_by("route__route_id").values_list(
        "shape_id", "route__route_id", "route__color", "route__agency__agency_id"
    ):
        route_of_shape.setdefault(shape_id, (route_id, route_color, agency_id))
    features = []
    for shape in Shape.objects.filter(feed=ctx.feed, pk__in=route_of_shape):
        route_id, route_color, agency_id = route_of_shape[shape.pk]
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": list(shape.geometry.coords)},
                "properties": {
                    "route_id": route_id,
                    "color": hex_color(route_color, "#888888"),
                    "agency": agency_id,
                },
            }
        )
    return Response({"type": "FeatureCollection", "features": features})


@api_view(["GET"])
@handles_errors
def plan(request, code):
    ctx = context_for(code)
    params = request.query_params
    return Response(
        queries.plan(
            ctx, params.get("from"), params.get("to"), parse_at(request, ctx), params.get("limit")
        )
    )


@api_view(["GET"])
@handles_errors
def departures(request, code, station_id):
    ctx = context_for(code)
    return Response(
        queries.departures(
            ctx, station_id, parse_at(request, ctx), request.query_params.get("limit")
        )
    )


@api_view(["GET"])
@handles_errors
def trip(request, code, trip_id):
    ctx = context_for(code)
    return Response(queries.trip_detail(ctx, trip_id, parse_date(request, ctx)))


@api_view(["GET"])
@handles_errors
def vehicles(request, code):
    return Response(queries.vehicles(context_for(code), agency=request.query_params.get("agency")))


@api_view(["GET"])
@handles_errors
def alerts(request, code):
    ctx = context_for(code)
    now = time.time()
    result = []
    for alert in Alert.objects.filter(operator=ctx.operator).order_by("alert_id"):
        periods = alert.active_periods or [[None, None]]
        if not any((s is None or s <= now) and (e is None or now < e) for s, e in periods):
            continue
        result.append(
            {
                "id": alert.alert_id,
                "header": alert.header,
                "description": alert.description,
                "url": alert.url,
                "cause": alert.cause,
                "effect": alert.effect,
                "active_periods": [
                    {
                        "start": iso(s and datetime.fromtimestamp(s, ctx.tz), ctx.tz),
                        "end": iso(e and datetime.fromtimestamp(e, ctx.tz), ctx.tz),
                    }
                    for s, e in alert.active_periods
                ],
                "route_ids": alert.route_ids,
                "stop_ids": alert.stop_ids,
            }
        )
    return Response(result)
