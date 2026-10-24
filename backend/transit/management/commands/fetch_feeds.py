from django.core.management.base import BaseCommand, CommandError

from transit.client import Client511Error
from transit.feeds import refresh
from transit.gtfs.importer import GTFSValidationError


class Command(BaseCommand):
    help = "Download static GTFS feeds from 511 and import any that changed"

    def add_arguments(self, parser):
        parser.add_argument(
            "operators", nargs="*", help="511 operator codes (default: TRANSIT_OPERATORS)"
        )

    def handle(self, operators, **options):
        try:
            results = refresh([code.upper() for code in operators] or None)
        except (Client511Error, GTFSValidationError, ValueError) as exc:
            raise CommandError(str(exc)) from None
        for result in results:
            verb = "Imported" if result.created else "Unchanged"
            self.stdout.write(self.style.SUCCESS(f"{verb}: {result.feed}"))
