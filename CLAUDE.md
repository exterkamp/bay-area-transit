# bay-area-transit

Django + PostGIS backend (`backend/`), Angular frontend (`frontend/`), 511.org
GTFS data. See README.md for commands and docs/api.md for the API contract.
The contract is the boundary: change it there first.

## Launch

- Backend (dev, autoreload, 127.0.0.1:8087):
  `docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d db backend worker`
- Frontend dev server: `devrun up --name web --port-env PORT -- "$PWD/frontend/scripts/dev.sh"`
  (absolute path: devrun does not start in the current directory).
- Full stack: `(cd frontend && npm run build) && docker compose up -d --build` → 127.0.0.1:8086.

## Gotchas

- This host's buildx is 0.10; compose needs `COMPOSE_BAKE=false` (set in `.env`).
- Docker's default address pools are exhausted here; the stack reuses the
  existing `bay-area-transit_default` network. Don't add networks without a subnet.
- 511 allows 60 requests/hour per key. `poll_realtime` and `fetch_feeds` spend
  them; don't loop them in tests. The worker enforces a budget at startup.
- `.env` is ignored, but commits before the Django 5.2 rebuild tracked one.
  Checking out such a commit silently overwrites `.env`, and coming back
  deletes it. Copy it aside first; `scripts/bootstrap.sh` only rebuilds it
  with a new secret key.
- Secrets in `secrets/` are 0644 inside a 0700 directory, on purpose: compose
  bind-mounts them with host permissions and containers run non-root.
- Datetimes are UTC internally; convert to the agency zone only in API output.
  Python offsets zoneinfo datetimes on the wall clock, which breaks DST days.
- Run backend tests in the container: `... run --rm backend python -m pytest`.
- Frontend typecheck is `npm run typecheck`; `tsc -p tsconfig.json` checks nothing.
