# API v1

Read-only JSON under `/api/v1`. No auth. Every list is small enough per
operator (Caltrain: ~30 stations, ~250 trips/day) that nothing is paginated;
the endpoints that could grow (`plan`, `departures`) take a `limit`.

Conventions:

- An **operator** is a 511 operator code: `CT` (Caltrain), `BA` (BART).
  Every operator-scoped endpoint reads the operator's *active* feed only.
- **Station ids** are GTFS `stop_id`s of parent stations (`location_type=1`),
  e.g. `22nd_street`. Platforms are children of a station.
- **Datetimes** are ISO 8601 with the agency's UTC offset,
  e.g. `2026-10-24T08:15:00-07:00`. **Dates** are `YYYY-MM-DD`.
- `at` query params accept an ISO datetime; a naive one is read in the
  agency's timezone. Omitted means now.
- Errors: `{"detail": "...", "code": "..."}`. 400 is `bad_request`; 404
  is `no_active_feed` when the operator exists but nothing is imported yet,
  else `not_found` (unknown operator, station or trip).
- "Today" and default dates are in the agency's timezone, and service dates
  follow GTFS: a train leaving at 00:20 can belong to the previous day.

## `GET /healthz`

`{"status": "ok"}`

## `GET /api/v1/operators`

```json
[
  {
    "code": "CT",
    "name": "Caltrain",
    "timezone": "America/Los_Angeles",
    "feed": {
      "version": "20260922",
      "start_date": "2026-01-31",
      "end_date": "2027-01-31",
      "imported_at": "2026-10-24T03:00:12-07:00"
    },
    "realtime": {
      "trip_updates_at": "2026-10-24T08:14:02-07:00",
      "vehicle_positions_at": "2026-10-24T08:14:05-07:00",
      "alerts_at": "2026-10-24T08:10:00-07:00"
    }
  }
]
```

`feed` is `null` until a feed has been imported. Any `realtime.*_at` is
`null` when that feed has never been polled; a value older than ~10 minutes
means realtime is stale and the UI should say so.

## `GET /api/v1/operators/{code}/stations`

Ordered north to south along the line (by the order stops appear on the
operator's longest trip), then alphabetically for anything not on it.

```json
[
  {
    "id": "22nd_street",
    "name": "22nd Street",
    "lat": 37.756972,
    "lon": -122.392492,
    "zone": "81789",
    "wheelchair_boarding": "unknown",
    "platforms": [
      {"id": "70021", "name": "22nd Street Caltrain Station Northbound", "platform_code": ""}
    ]
  }
]
```

`wheelchair_boarding`: `"unknown" | "accessible" | "inaccessible"`.

## `GET /api/v1/operators/{code}/routes`

```json
[
  {"id": "Limited", "short_name": "Limited", "long_name": "", "type": 2,
   "color": "#99d7dc", "text_color": "#000000"}
]
```

Colors are always `#rrggbb` (defaults `#888888` / `#000000` when the feed
leaves them blank).

## `GET /api/v1/operators/{code}/shapes`

GeoJSON `FeatureCollection`, one `LineString` feature per distinct shape,
`properties: {"route_id": "Limited", "color": "#99d7dc"}`. Coordinates are
`[lon, lat]` as GeoJSON requires.

## `GET /api/v1/operators/{code}/plan?from=&to=&at=&limit=10`

Next trains from station `from` to station `to` that depart at or after
`at`. `limit` 1-50, default 10. Searches the service day of `at` and the
previous one (for trips running past midnight), and the next one if fewer
than `limit` were found.

```json
{
  "from": {"id": "palo_alto", "name": "Palo Alto"},
  "to": {"id": "san_francisco", "name": "San Francisco"},
  "at": "2026-10-24T08:00:00-07:00",
  "fare": {"price": "6.75", "currency": "USD"},
  "trips": [
    {
      "trip_id": "401",
      "service_date": "2026-10-24",
      "short_name": "401",
      "headsign": "San Francisco",
      "direction": 0,
      "route": {"id": "Limited", "short_name": "Limited", "color": "#99d7dc", "text_color": "#000000"},
      "status": "scheduled",
      "depart": {
        "stop_id": "70171",
        "platform": "Palo Alto Caltrain Station Northbound",
        "scheduled": "2026-10-24T08:05:00-07:00",
        "estimated": "2026-10-24T08:07:00-07:00",
        "delay_seconds": 120
      },
      "arrive": {
        "stop_id": "70011",
        "platform": "San Francisco Caltrain Station",
        "scheduled": "2026-10-24T08:52:00-07:00",
        "estimated": null,
        "delay_seconds": null
      },
      "duration_minutes": 47,
      "stops_between": 6
    }
  ]
}
```

- `status`: `"scheduled"` (no realtime for this trip), `"live"` (realtime
  data present), `"canceled"` (realtime says the trip or the boarding stop
  is canceled). Canceled trips are still returned so the UI can show them
  struck through.
- `estimated`/`delay_seconds` are `null` without realtime for that stop.
- `duration_minutes` is scheduled. `stops_between` counts every scheduled
  call between the two, including ones realtime says will be skipped.
- `fare` is the base (adult) fare from `fare_attributes.txt`, `null` when
  no fare rule matches. Discount categories aren't modelled.
- Only direct trains are found. A trip that needs a transfer (e.g. San
  Francisco to Gilroy, via the South County connector at San Jose) returns
  no trips.
- 400 if `from == to`, or either is missing.

## `GET /api/v1/operators/{code}/stations/{station_id}/departures?at=&limit=20`

Departure board for one station, both directions, same trip shape as `plan`
but with only `depart` and a `destination` instead of `arrive`:

```json
{
  "station": {"id": "palo_alto", "name": "Palo Alto"},
  "at": "2026-10-24T08:00:00-07:00",
  "departures": [
    {
      "trip_id": "401", "service_date": "2026-10-24", "short_name": "401",
      "headsign": "San Francisco", "direction": 0,
      "route": {"id": "Limited", "short_name": "Limited", "color": "#99d7dc", "text_color": "#000000"},
      "status": "live",
      "depart": {"stop_id": "70171", "platform": "...", "scheduled": "...", "estimated": "...", "delay_seconds": 120},
      "destination": {"id": "san_francisco", "name": "San Francisco"}
    }
  ]
}
```

The last stop of a trip is never listed as a departure. Like `plan`, the
board runs on into the next service day, so an empty board means nothing
is scheduled for over a day.

## `GET /api/v1/operators/{code}/trips/{trip_id}?date=YYYY-MM-DD`

`date` is the service date, default today. 404 if the trip does not run
that day.

```json
{
  "trip_id": "401", "service_date": "2026-10-24", "short_name": "401",
  "headsign": "San Francisco", "direction": 0,
  "route": {"id": "Limited", "short_name": "Limited", "color": "#99d7dc", "text_color": "#000000"},
  "status": "live",
  "bikes_allowed": true,
  "wheelchair_accessible": true,
  "stops": [
    {
      "sequence": 1, "stop_id": "70261", "station_id": "tamien", "name": "Tamien",
      "arrival": {"scheduled": "...", "estimated": null, "delay_seconds": null},
      "departure": {"scheduled": "...", "estimated": null, "delay_seconds": null},
      "skipped": false
    }
  ],
  "vehicle": null
}
```

`vehicle` has the shape of one entry of `/vehicles`, or `null`.

## `GET /api/v1/operators/{code}/vehicles`

Latest vehicle positions. Empty list when realtime is stale (>10 minutes);
use `/operators` `realtime.vehicle_positions_at` to tell stale from "no
trains running". `stop_id` is a platform id, as in `trips[].stops[].stop_id`.

```json
[
  {
    "vehicle_id": "128", "trip_id": "401", "short_name": "401",
    "route": {"id": "Limited", "short_name": "Limited", "color": "#99d7dc", "text_color": "#000000"},
    "headsign": "San Francisco",
    "lat": 37.44, "lon": -122.16, "bearing": null,
    "status": "in_transit_to", "stop_id": "70171",
    "timestamp": "2026-10-24T08:14:00-07:00"
  }
]
```

`status`: `"incoming_at" | "stopped_at" | "in_transit_to" | null`.
`bearing` (degrees) and `stop_id` are `null` when the feed omits them;
511's Caltrain feed currently sends neither, nor `status`.
`route`/`short_name`/`headsign` are `null` if the trip is not in the
static feed.

## `GET /api/v1/operators/{code}/alerts`

Alerts active now.

```json
[
  {
    "id": "alert-123",
    "header": "Delays near Millbrae",
    "description": "Trains are running up to 15 minutes late.",
    "url": "",
    "cause": "technical_problem",
    "effect": "significant_delays",
    "active_periods": [{"start": "2026-10-24T07:30:00-07:00", "end": null}],
    "route_ids": ["Local Weekday"],
    "stop_ids": ["70111"]
  }
]
```

`cause`/`effect` are the GTFS-realtime enum names, lowercased.
