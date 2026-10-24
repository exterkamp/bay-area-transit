from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from transit.client import Client511, Client511Error
from transit.models import Operator, RealtimeKind
from transit.realtime.poller import poll


class Command(BaseCommand):
    help = "Poll GTFS-realtime feeds once (each feed is one 511 request)"

    def add_arguments(self, parser):
        parser.add_argument("operators", nargs="*", help="default: TRANSIT_REALTIME_OPERATORS")
        parser.add_argument("--kind", choices=RealtimeKind.values, action="append")

    def handle(self, operators, kind, **options):
        codes = [c.upper() for c in operators] or settings.TRANSIT["REALTIME_OPERATORS"]
        client = Client511()
        failed = False
        for code in codes:
            operator = Operator.objects.filter(code=code).first()
            if operator is None:
                raise CommandError(f"unknown operator {code}; import its static feed first")
            for k in kind or RealtimeKind.values:
                try:
                    count = poll(operator, k, client)
                    self.stdout.write(f"{code} {k}: {count}")
                except Client511Error as exc:
                    failed = True
                    self.stderr.write(f"{code} {k}: {exc}")
        if failed:
            raise CommandError("some feeds failed")
