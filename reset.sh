#!/usr/bin/env bash
set -x

echo "Destroying stack."
docker compose down -v

echo "Destroying migrations."
rm -f bayareatransit/backend/migrations/000*py