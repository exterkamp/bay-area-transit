"""A small client for the 511.org open data API.

511 authenticates with an ``api_key`` query parameter, so request URLs are
secrets. Nothing here logs a URL, and errors are re-raised with the key
scrubbed out.
"""

import json
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

REALTIME_PATHS = {
    "trip_updates": "/transit/tripupdates",
    "vehicle_positions": "/transit/vehiclepositions",
    "alerts": "/transit/servicealerts",
}


class Client511Error(Exception):
    pass


class RateLimited(Client511Error):
    pass


class Client511:
    def __init__(self, api_key=None, base_url=None, timeout=60):
        self.api_key = api_key if api_key is not None else settings.TRANSIT["API_KEY"]
        self.base_url = (base_url or settings.TRANSIT["BASE_URL"]).rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "bay-area-transit/0.2"
        self.remaining = None
        if not self.api_key:
            raise Client511Error("TRANSIT_511_API_KEY is not set")

    def _scrub(self, text):
        return str(text).replace(self.api_key, "***")

    def get(self, path, **params) -> bytes:
        params["api_key"] = self.api_key
        try:
            response = self.session.get(self.base_url + path, params=params, timeout=self.timeout)
        except requests.RequestException as exc:
            raise Client511Error(f"GET {path} failed: {self._scrub(exc)}") from None
        remaining = response.headers.get("RateLimit-Remaining")
        if remaining is not None:
            self.remaining = int(remaining)
            if self.remaining < 5:
                logger.warning("511 rate limit nearly exhausted: %s requests left", remaining)
        if response.status_code == 429:
            raise RateLimited(f"GET {path}: rate limited by 511")
        if response.status_code != 200:
            body = self._scrub(response.text[:200])
            raise Client511Error(f"GET {path}: HTTP {response.status_code} {body}")
        return response.content

    def operators(self) -> list[dict]:
        # 511 prefixes its JSON with a UTF-8 byte order mark.
        return json.loads(self.get("/transit/operators", format="json").decode("utf-8-sig"))

    def static_feed(self, operator_code) -> bytes:
        return self.get("/transit/datafeeds", operator_id=operator_code)

    def realtime(self, kind, operator_code) -> bytes:
        return self.get(REALTIME_PATHS[kind], agency=operator_code)
