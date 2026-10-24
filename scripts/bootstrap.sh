#!/usr/bin/env bash
# One-time setup: write .env and the secret files docker compose mounts.
# Idempotent; never overwrites a secret that already exists.
set -euo pipefail
cd "$(dirname "$0")/.."

mkdir -p secrets
# The directory is the lock: 0700 keeps other host users out. The files
# themselves must be world-readable because compose bind-mounts them with
# host permissions, and the containers run as non-root users.
chmod 700 secrets

random() { python3 -c 'import secrets; print(secrets.token_urlsafe(48))'; }

if [ ! -f .env ]; then
  cp .env.example .env
  sed -i "s|^DJANGO_SECRET_KEY=.*|DJANGO_SECRET_KEY=$(random)|" .env
  chmod 600 .env
  echo "wrote .env"
fi

if [ ! -f secrets/postgres_password ]; then
  random > secrets/postgres_password
  chmod 644 secrets/postgres_password
  echo "wrote secrets/postgres_password"
fi

if [ ! -f secrets/transit_511_api_key ]; then
  if [ -f secrets/api.cfg ]; then
    # Carry the key over from the old configparser file.
    python3 - <<'PY'
import configparser, os
c = configparser.ConfigParser()
c.read("secrets/api.cfg")
with open("secrets/transit_511_api_key", "w") as f:
    f.write(c.get("api", "API_KEY").strip() + "\n")
os.chmod("secrets/transit_511_api_key", 0o644)
PY
    echo "wrote secrets/transit_511_api_key (from secrets/api.cfg)"
  else
    echo "Put your 511.org API key in secrets/transit_511_api_key" >&2
    echo "(request one at https://511.org/open-data/token)" >&2
    exit 1
  fi
fi
