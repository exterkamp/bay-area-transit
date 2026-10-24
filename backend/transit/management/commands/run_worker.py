"""The long-running poller: static feeds daily, realtime every few minutes.

One process, one loop, one schedule: every job has a next-due time and the
loop sleeps until the earliest one. Before starting it checks the schedule
against 511's per-key hourly limit, because overshooting gets every request
rejected, which is worse than polling a little less often.
"""

import logging
import signal
import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from transit.client import Client511, Client511Error, RateLimited
from transit.feeds import ensure_operators, refresh
from transit.gtfs.importer import GTFSValidationError
from transit.models import RealtimeKind
from transit.realtime.poller import poll

logger = logging.getLogger("transit.worker")

INTERVAL_SETTING = {
    RealtimeKind.TRIP_UPDATES: "POLL_TRIP_UPDATES",
    RealtimeKind.VEHICLE_POSITIONS: "POLL_VEHICLE_POSITIONS",
    RealtimeKind.ALERTS: "POLL_ALERTS",
}
RATE_LIMIT_BACKOFF = 15 * 60
FAILURE_BACKOFF = 5 * 60


def hourly_requests(cfg) -> float:
    realtime = sum(3600 / cfg[INTERVAL_SETTING[k]] for k in RealtimeKind.values)
    static = len(cfg["OPERATORS"]) / cfg["STATIC_REFRESH_HOURS"]
    return realtime * len(cfg["REALTIME_OPERATORS"]) + static


class Command(BaseCommand):
    help = "Run the feed refresher and realtime poller until stopped"

    def handle(self, **options):
        cfg = settings.TRANSIT
        planned = hourly_requests(cfg)
        if planned > cfg["HOURLY_REQUEST_BUDGET"]:
            raise CommandError(
                f"schedule needs {planned:.0f} requests/hour, over the budget of "
                f"{cfg['HOURLY_REQUEST_BUDGET']}; poll less often or for fewer operators"
            )
        logger.info("Worker starting: ~%.0f 511 requests/hour", planned)

        self.running = True
        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)

        client = Client511()
        realtime_ops = ensure_operators(cfg["REALTIME_OPERATORS"], client)
        now = time.monotonic()
        # (due, name, interval, action). Static first, so realtime has a
        # schedule to attach to on a fresh install.
        jobs = [[now, "static", cfg["STATIC_REFRESH_HOURS"] * 3600, lambda: refresh(client=client)]]
        for i, op in enumerate(realtime_ops):
            for j, kind in enumerate(RealtimeKind.values):
                # Stagger first polls so they don't all land in the same second.
                jobs.append(
                    [
                        now + 5 + 3 * (i * 3 + j),
                        f"{op.code} {kind}",
                        cfg[INTERVAL_SETTING[kind]],
                        lambda op=op, kind=kind: poll(op, kind, client),
                    ]
                )

        while self.running:
            job = min(jobs, key=lambda j: j[0])
            wait = job[0] - time.monotonic()
            if wait > 0:
                self.sleep(wait)
                continue
            due, name, interval, action = job
            try:
                action()
                job[0] = time.monotonic() + interval
            except RateLimited:
                logger.warning("%s: rate limited; backing everything off", name)
                for other in jobs:
                    other[0] = max(other[0], time.monotonic() + RATE_LIMIT_BACKOFF)
            except (Client511Error, GTFSValidationError, ValueError) as exc:
                logger.error("%s failed: %s", name, exc)
                job[0] = time.monotonic() + min(interval, FAILURE_BACKOFF)
            except Exception:
                logger.exception("%s crashed", name)
                job[0] = time.monotonic() + min(interval, FAILURE_BACKOFF)
        logger.info("Worker stopped")

    def stop(self, *args):
        self.running = False

    def sleep(self, seconds):
        end = time.monotonic() + seconds
        while self.running and time.monotonic() < end:
            time.sleep(min(1.0, end - time.monotonic()))
