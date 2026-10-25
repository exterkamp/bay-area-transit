# API v1

Read-only JSON under `/api/v1`. No auth. Nothing is paginated: lists that
could grow take a `limit` (`plan`, `departures`, `places`) or a filter
(`stations`, `shapes`, `vehicles`).

Conventions:

- An **operator** is a 511 operator code and names a data source: `RG`
  (511's regional feed, which this app imports filtered to Muni rail, BART,
  SamTrans and Caltrain), or a single agency's own feed such as `CT`. Every
  operator-scoped endpoint reads the operator's *active* feed only.
- An **agency** is a GTFS `agency_id` within that feed: in `RG`, `SF`
  (Muni), `BA` (BART), `SM` (SamTrans), `CT` (Caltrain). Endpoints that
  take `agency=` accept a comma-separated list.
- A **place** is what a rider picks as an origin, destination or board.
  It's either a station (a GTFS `location_type=1` stop, whose platforms are
  where you board) or a group of free-standing stops with the same name
  within 300 m of each other, such as the two sides of the street at
  "Church St & 16th St". A **place id** is the station's `stop_id`, or the
  lowest `stop_id` in the group. Wherever a place id is accepted, the
  `stop_id` of any stop in the place works too and resolves to the place.
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
    },
    "agencies": ["CT"]
  }
]
```

`feed` is `null` until a feed has been imported. Any `realtime.*_at` is
`null` when that feed has never been polled; a value older than ~10 minutes
means realtime is stale and the UI should say so.

## `GET /api/v1/operators/{code}/agencies`

```json
[
  {"id": "BA", "name": "Bay Area Rapid Transit", "url": "https://www.bart.gov",
   "timezone": "America/Los_Angeles", "route_types": [1, 3], "places": 50,
   "feed": {"version": "20261019", "start_date": "2026-08-10", "end_date": "2027-01-10"}}
]
```

`route_types` lists the GTFS route types the feed has for that agency
(0 light rail, 1 subway, 2 rail, 3 bus, 5 cable car). `places` counts the
places its routes call at: a client can list a small agency's stations
whole and ask for a line first on a big one.

`feed` is the agency's own timetable inside a merged feed (511's regional
feed lists one per agency), or `null` when the feed doesn't say. A merged
feed's own `start_date`/`end_date` in `/operators` is when all of its
agencies' timetables are valid: from the latest start to the earliest end,
so its `end_date` is when the first one runs out.

## Places

Every endpoint below that returns a place uses this shape:

```json
{
  "id": "mtc:powell",
  "name": "Powell",
  "kind": "station",
  "lat": 37.78445,
  "lon": -122.40792,
  "zone": "",
  "wheelchair_boarding": "unknown",
  "agencies": ["BA", "SF"],
  "routes": [
    {"id": "BA:Blue-N", "short_name": "Blue-N", "color": "#0099d8",
     "text_color": "#ffffff", "agency": "BA", "type": 1}
  ],
  "platforms": [
    {"id": "16995", "name": "Powell Station Outbound", "platform_code": ""}
  ]
}
```

- `kind`: `"station"` or `"stop"` (a group of free-standing stops).
- `routes` are the routes with a trip that calls there, by agency then
  name. `platforms` are where you board: a station's platforms, or the
  stops in a group.
- `wheelchair_boarding`: `"unknown" | "accessible" | "inaccessible"`.

## `GET /api/v1/operators/{code}/places?q=&near=&radius=&agency=&limit=20`

Search, for pickers. Needs `q`, `near`, or both.

- `q` (2+ characters) matches names forgivingly: `powel`, `16th church`,
  `millbrae`. Best matches come first, then shorter names.
- `near=lat,lon` keeps places within `radius` meters (default 1000, max
  5000) and orders by distance. With `q` too, it only orders.
- `agency` keeps places served by any of the listed agencies.
- `limit` 1-50.

```json
{"places": [{"id": "mtc:powell", "...": "...", "distance_m": 120}]}
```

`distance_m` is present only with `near`. 400 for a short `q`, a bad
`near` or `radius`, or neither `q` nor `near`.

## `GET /api/v1/operators/{code}/places/{place_id}`

One place. A member `stop_id` returns its place, whose `id` is then the
place id to store.

## `GET /api/v1/operators/{code}/stations?agency=&route=`

The places on a line or network, in line order: a topological merge of
every stopping pattern on the matching trips, north end first, so branches
sit where they join. Items are places, as above.

Without `agency` or `route` this lists the whole feed, which is only
allowed when the feed has one agency (as `CT` or `BA` do). On a
multi-agency feed it's a 400 with code `filter_required`: use `places`
to search instead.

## `GET /api/v1/operators/{code}/routes?agency=`

```json
[
  {"id": "Limited", "short_name": "Limited", "long_name": "", "type": 2,
   "color": "#99d7dc", "text_color": "#000000", "agency": "CT"}
]
```

A **route summary**, as embedded in trips and vehicles below, is the same
without `long_name`: `{"id", "short_name", "color", "text_color",
"agency", "type"}`. Its `short_name` falls back to the long name.

Colors are always `#rrggbb` (defaults `#888888` / `#000000` when the feed
leaves them blank).

## `GET /api/v1/operators/{code}/shapes?agency=&route=`

GeoJSON `FeatureCollection`, one `LineString` feature per distinct shape,
`properties: {"route_id": "Limited", "color": "#99d7dc", "agency": "CT"}`. Coordinates are
`[lon, lat]` as GeoJSON requires.

## `GET /api/v1/operators/{code}/plan?from=&to=&at=&limit=10&agency=&route=`

Next direct trips from place `from` to place `to` that depart at or after
`at`, on any agency that serves both. `agency` (comma-separated ids) or
`route` (a route id) keeps only those trips, and `served` then says whether
they ever go from one to the other. `limit` 1-50, default 10. Searches the service day of `at` and the
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
      "route": {"id": "Limited", "short_name": "Limited", "color": "#99d7dc",
                "text_color": "#000000", "agency": "CT", "type": 2},
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
- `from` and `to` in the response are places, `{"id", "name"}`, even when
  a member stop id was passed.
- `served` (present only when `trips` is empty) says whether any trip in
  the timetable runs directly from `from` to `to`, on any day. True means
  nothing runs in the searched window (about a day) but the trip exists,
  e.g. a weekday-only ferry asked on a Saturday evening; false means it
  needs a transfer.
- Only direct trips are found. A journey that needs a transfer (e.g. San
  Francisco to Gilroy, via the South County connector at San Jose, or
  BART to Caltrain at Millbrae) returns no trips.
- 400 if `from` and `to` are the same place, or either is missing.

## `GET /api/v1/operators/{code}/stations/{place_id}/departures?at=&limit=20`

Departure board for one place, every agency there, both directions, same trip shape as `plan`
but with only `depart` and a `destination` instead of `arrive`:

```json
{
  "station": {"id": "palo_alto", "name": "Palo Alto"},
  "at": "2026-10-24T08:00:00-07:00",
  "departures": [
    {
      "trip_id": "401", "service_date": "2026-10-24", "short_name": "401",
      "headsign": "San Francisco", "direction": 0,
      "route": {"id": "Limited", "short_name": "Limited", "color": "#99d7dc", "text_color": "#000000", "agency": "CT", "type": 2},
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
that day. `stops[].station_id` is the place id of each stop.

```json
{
  "trip_id": "401", "service_date": "2026-10-24", "short_name": "401",
  "headsign": "San Francisco", "direction": 0,
  "route": {"id": "Limited", "short_name": "Limited", "color": "#99d7dc", "text_color": "#000000", "agency": "CT", "type": 2},
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

## `GET /api/v1/operators/{code}/vehicles?agency=`

Where vehicles are now, filtered by the trip's agency when `agency` is
given. Two kinds, told apart by `source`:

- `"gps"`: a position the agency reported (GTFS-realtime vehicle
  positions). Muni, SamTrans and Caltrain send these.
- `"estimated"`: computed from the trip's live predictions for a trip
  with no GPS report: between its last departure and next arrival,
  placed along the route's shape in proportion to the time elapsed, or
  at the platform while it's due to be standing there. BART sends no
  positions, so all BART vehicles are estimated.

The list is computed for the whole feed at most every 10 seconds and
shared by all requests, so polling faster than that returns the same
snapshot. Empty list when realtime is stale (>10 minutes): GPS needs fresh vehicle
positions, estimates need fresh trip updates. Use `/operators`
`realtime.*_at` to tell stale from "nothing running". `stop_id` is a
platform id, as in `trips[].stops[].stop_id`.

```json
[
  {
    "vehicle_id": "128", "trip_id": "401", "short_name": "401",
    "route": {"id": "Limited", "short_name": "Limited", "color": "#99d7dc", "text_color": "#000000", "agency": "CT", "type": 2},
    "headsign": "San Francisco",
    "lat": 37.44, "lon": -122.16, "bearing": null,
    "status": "in_transit_to", "stop_id": "70171",
    "timestamp": "2026-10-24T08:14:00-07:00",
    "source": "gps"
  }
]
```

- `vehicle_id` is `null` when the feed doesn't name the vehicle (some
  estimated ones); key markers by `vehicle_id`, else `trip_id`.
- `status`: `"incoming_at" | "stopped_at" | "in_transit_to" | null`.
  Estimates are always `stopped_at` or `in_transit_to`.
- `bearing` (degrees) and `stop_id` are `null` when the feed omits them;
  511's Caltrain GPS sends neither, nor `status`. Estimates take their
  bearing from the shape when the trip has one.
- `timestamp` is when the GPS fix was taken, or for an estimate, the
  moment it was computed (the request).
- `route`/`short_name`/`headsign` are `null` if the trip is not in the
  static feed (GPS only: estimates always have a static trip).

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
    "stop_ids": ["70111"],
    "agencies": ["CT"]
  }
]
```

`cause`/`effect` are the GTFS-realtime enum names, lowercased.
`agencies` are the agencies the alert is about: those it names, plus the
agencies of its routes and of the routes serving its stops, sorted. Empty
when none of those are in the static feed.
