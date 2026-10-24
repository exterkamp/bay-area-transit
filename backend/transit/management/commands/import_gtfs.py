from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from transit.gtfs.importer import FeedFilter, GTFSValidationError, import_feed
from transit.models import Operator


class Command(BaseCommand):
    help = "Import a GTFS archive (zip or extracted folder) for an operator"

    def add_arguments(self, parser):
        parser.add_argument("source", help="Path to a GTFS .zip or an extracted folder")
        parser.add_argument("--operator", required=True, help="511 operator code, e.g. CT")
        parser.add_argument(
            "--no-activate", action="store_true", help="Import but keep it inactive"
        )
        parser.add_argument(
            "--agencies",
            help="Feed filter, e.g. 'SF:0,BA,SM,CT' (default: the operator's FEED_FILTERS entry)",
        )

    def handle(self, source, operator, no_activate, agencies, **options):
        op, _ = Operator.objects.get_or_create(code=operator.upper(), defaults={"name": ""})
        spec = agencies if agencies is not None else settings.TRANSIT["FEED_FILTERS"].get(op.code)
        try:
            result = import_feed(
                op,
                source,
                activate=not no_activate,
                keep=settings.TRANSIT["KEEP_FEEDS"],
                only=FeedFilter.parse(spec),
            )
        except (GTFSValidationError, ValueError) as exc:
            raise CommandError(str(exc)) from None
        feed = result.feed
        verb = "Imported" if result.created else "Already had"
        self.stdout.write(self.style.SUCCESS(f"{verb} {feed}"))
        if "filter" in feed.stats:
            self.stdout.write(f"  filter: {feed.stats['filter']}")
        self.stdout.write(f"  counts: {feed.stats.get('counts')}")
        for warning in feed.stats.get("warnings", [])[:20]:
            self.stdout.write(f"  warning: {warning}")
