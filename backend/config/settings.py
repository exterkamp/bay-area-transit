"""Django settings, configured entirely from the environment.

Production is the default: DEBUG is off and a missing DJANGO_SECRET_KEY is an
error. Set DJANGO_DEBUG=1 for local development.
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def env(name, default=None):
    return os.environ.get(name, default)


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name, default=""):
    return [item.strip() for item in env(name, default).split(",") if item.strip()]


def env_secret(name, default=None):
    """Read NAME, or the contents of the file named by NAME_FILE (docker secrets)."""
    path = env(f"{name}_FILE")
    if path:
        return Path(path).read_text().strip()
    return env(name, default)


DEBUG = env_bool("DJANGO_DEBUG")

SECRET_KEY = env_secret("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured("DJANGO_SECRET_KEY is required when DJANGO_DEBUG is off")
    SECRET_KEY = "insecure-dev-only-key"

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,backend")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.gis",
    "rest_framework",
    "transit",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.contrib.gis.db.backends.postgis",
        "NAME": env("POSTGRES_DB", "transit"),
        "USER": env("POSTGRES_USER", "transit"),
        "PASSWORD": env_secret("POSTGRES_PASSWORD", ""),
        "HOST": env("POSTGRES_HOST", "db"),
        "PORT": int(env("POSTGRES_PORT", "5432")),
        "CONN_MAX_AGE": 60,
        "CONN_HEALTH_CHECKS": True,
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "America/Los_Angeles"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "UNAUTHENTICATED_USER": None,
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"]
    + (["rest_framework.renderers.BrowsableAPIRenderer"] if DEBUG else []),
}

# Behind nginx (and later Traefik), which terminate TLS.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
    "loggers": {
        # urllib3 logs full request URLs at DEBUG, and 511 takes the API key as a
        # query parameter. Never let that reach the logs.
        "urllib3": {"level": "WARNING"},
    },
}

# --- 511.org -----------------------------------------------------------------

TRANSIT = {
    "API_KEY": env_secret("TRANSIT_511_API_KEY", ""),
    "BASE_URL": env("TRANSIT_511_BASE_URL", "https://api.511.org"),
    # Operators whose static GTFS feed is downloaded and imported.
    "OPERATORS": env_list("TRANSIT_OPERATORS", "CT,BA"),
    # Which agencies (and route types) to keep from multi-agency feeds, per
    # operator. RG is 511's merged regional feed of ~41 agencies. Spec syntax
    # is in transit.gtfs.importer.FeedFilter: here Muni rail only (type 0:
    # Metro and the F), and BART, SamTrans and Caltrain whole.
    "FEED_FILTERS": {"RG": env("TRANSIT_RG_AGENCIES", "SF:0,BA,SM,CT")},
    # Operators whose GTFS-realtime feeds are polled. Each one costs requests.
    "REALTIME_OPERATORS": env_list("TRANSIT_REALTIME_OPERATORS", "CT"),
    # Seconds between polls of each realtime feed, per operator.
    "POLL_TRIP_UPDATES": int(env("TRANSIT_POLL_TRIP_UPDATES", "180")),
    "POLL_VEHICLE_POSITIONS": int(env("TRANSIT_POLL_VEHICLE_POSITIONS", "180")),
    "POLL_ALERTS": int(env("TRANSIT_POLL_ALERTS", "600")),
    "STATIC_REFRESH_HOURS": float(env("TRANSIT_STATIC_REFRESH_HOURS", "24")),
    # 511 allows 60 requests/hour per key. The worker refuses a schedule that
    # would exceed this, leaving headroom for static refreshes and retries.
    "HOURLY_REQUEST_BUDGET": int(env("TRANSIT_511_HOURLY_BUDGET", "55")),
    # Realtime older than this is ignored by the API.
    "REALTIME_MAX_AGE": int(env("TRANSIT_REALTIME_MAX_AGE", "600")),
    # How many imported feeds to keep per operator (the active one included).
    "KEEP_FEEDS": int(env("TRANSIT_KEEP_FEEDS", "2")),
}
