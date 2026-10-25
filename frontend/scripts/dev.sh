#!/bin/sh
# Dev server for devrun: `devrun up --name web --port-env PORT -- ./scripts/dev.sh`
# ng serve ignores $PORT, so pass it explicitly. /api and /healthz are proxied
# to the Django backend on 127.0.0.1:8087 (proxy.conf.json). Listens on all
# interfaces so other devices on the LAN can reach it; set HOST to narrow it.
set -e
cd "$(dirname "$0")/.."
. "$HOME/.nvm/nvm.sh" >/dev/null
nvm use 24 >/dev/null
export NODE_OPTIONS="${NODE_OPTIONS:---max-old-space-size=2048}"
exec npx ng serve --proxy-config proxy.conf.json --host "${HOST:-0.0.0.0}" --port "${PORT:-4300}"
