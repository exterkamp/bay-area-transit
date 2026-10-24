# syntax=docker/dockerfile:1
FROM python:3.13-slim-bookworm

# GeoDjango loads GDAL/GEOS/PROJ as shared libraries; no Python GDAL bindings needed.
RUN apt-get update \
    && apt-get install -y --no-install-recommends binutils gdal-bin libproj25 curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.8.22 /uv /bin/uv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/venv \
    PATH="/venv/bin:$PATH"

WORKDIR /app
ARG UV_GROUPS="--no-dev"
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked $UV_GROUPS

COPY . .
RUN DJANGO_DEBUG=1 python manage.py collectstatic --noinput \
    && useradd --system --uid 10001 app
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD curl -fsS http://localhost:8000/healthz || exit 1
ENTRYPOINT ["./entrypoint.sh"]
CMD ["serve"]
