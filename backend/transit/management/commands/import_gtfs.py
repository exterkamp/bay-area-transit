from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from transit.gtfs.importer import GTFSValidationError, import_feed
from transit.models import Operator


class Command(BaseCommand):
    help = "Import a GTFS archive (zip or extracted folder) for an operator"

    def add_arguments(self, parser):
        parser.add_argument("source", help="Path to a GTFS .zip or an extracted folder")
        parser.add_argument("--operator", required=True, help="511 operator code, e.g. CT")
        parser.add_argument(
            "--no-activate", action="store_true", help="Import but keep it inactive"
        )

    def handle(self, source, operator, no_activate, **options):
        op, _ = Operator.objects.get_or_create(code=operator.upper(), defaults={"name": ""})
        try:
            result = import_feed(
                op, source, activate=not no_activate, keep=settings.TRANSIT["KEEP_FEEDS"]
            )
        except GTFSValidationError as exc:
            raise CommandError(str(exc)) from None
        feed = result.feed
        verb = "Imported" if result.created else "Already had"
        self.stdout.write(self.style.SUCCESS(f"{verb} {feed}"))
        for warning in feed.stats.get("warnings", [])[:20]:
            self.stdout.write(f"  warning: {warning}")
