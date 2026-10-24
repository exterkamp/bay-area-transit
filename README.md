# bay-area-transit

Caltrain (and BART) schedules with live delays, built on the
[511.org open data](https://511.org/open-data/transit) GTFS and
GTFS-realtime feeds.

- **backend/**: Django 5.2 + PostGIS. Imports static GTFS feeds into a
  constrained schema, polls GTFS-realtime, and serves a read-only JSON API
  ([docs/api.md](docs/api.md)): trip planning, departure boards, trip
  detail, live vehicles and alerts.
- **frontend/**: Angular 22. Trip planner, station boards, trip detail and
  a Leaflet map with live trains.
- **docker-compose.yml**: `db` (PostGIS), `backend` (gunicorn), `worker`
  (feed refresh and realtime poller) and `web` (nginx serving the built
  frontend and proxying `/api`).

## Setup

```sh
./scripts/bootstrap.sh     # writes .env and secrets/, once
```

It needs a 511 API key ([request one](https://511.org/open-data/token)) in
`secrets/transit_511_api_key`. If the old `secrets/api.cfg` is there, the key
is copied from it.

## Run it

```sh
(cd frontend && npm ci && npm run build)
docker compose up -d --build
open http://127.0.0.1:8086
```

On first start the worker downloads and imports the feeds (about 15
seconds for Caltrain and BART), then starts polling realtime.

## Develop

```sh
# Backend with autoreload on 127.0.0.1:8087
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d db backend worker

# Frontend dev server, proxying /api to 8087
devrun up --name web --port-env PORT -- "$PWD/frontend/scripts/dev.sh"
devrun url web
```

Tests:

```sh
DC="docker compose -f docker-compose.yml -f docker-compose.dev.yml"
$DC run --rm backend python -m pytest      # backend, against a throwaway PostGIS db
$DC run --rm backend ruff check .
(cd frontend && npm test && npm run typecheck)
```

Useful management commands (`$DC exec backend python manage.py ...`):

| Command | Does |
|---|---|
| `fetch_feeds [CT BA]` | Download static feeds from 511, import any that changed |
| `import_gtfs path.zip --operator CT` | Import a local archive or folder |
| `poll_realtime [CT] [--kind alerts]` | Poll realtime once |
| `run_worker` | What the `worker` service runs |
| `createsuperuser` | For `/admin/` (read-only browsing), at http://127.0.0.1:8087/admin/ only: the `web` container deliberately doesn't proxy it |

## 511 rate limit

511 allows **60 requests/hour per API key**, shared by everything that
uses the key. At the default intervals, realtime for one operator costs 46
requests/hour (trip updates and vehicle positions every 3 minutes, alerts
every 10), and the worker refuses to start with a schedule over
`TRANSIT_511_HOURLY_BUDGET` (55). That's why realtime is on for Caltrain
only. Static feeds are checked once a day and only re-imported when the
archive changes.

## Data model

Every GTFS table carries its `feed`. GTFS ids are unique per feed, and
enums and conditional requirements are check constraints. Times are
seconds after the start of the service day, so 25:10:00 works. The importer
runs in one transaction and rejects a feed whole, listing every problem by
file and line. Untimed stops are interpolated, and a new feed becomes active
only once it is complete. Realtime is stored as replaceable snapshots keyed
by GTFS ids, never foreign keys, so a feed swap can't break it. See the
docstrings in `backend/transit/models/`.

Not modelled: frequencies.txt, transfers.txt, fare products beyond the base
fare, and journeys that need a transfer (San Francisco to Gilroy changes
at San Jose for the South County connector).
