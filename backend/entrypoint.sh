#!/bin/sh
set -eu

case "${1:-serve}" in
  serve)
    python manage.py migrate --noinput
    exec gunicorn config.wsgi \
      --no-control-socket \
      --bind 0.0.0.0:8000 \
      --workers "${GUNICORN_WORKERS:-3}" \
      --access-logfile - \
      --forwarded-allow-ips '*'
    ;;
  dev)
    python manage.py migrate --noinput
    exec python manage.py runserver 0.0.0.0:8000
    ;;
  worker)
    exec python manage.py run_worker
    ;;
  *)
    exec "$@"
    ;;
esac
