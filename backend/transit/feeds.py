"""Download static feeds from 511 and import the ones that changed."""

import logging

from django.conf import settings

from transit.client import Client511
from transit.gtfs.importer import ImportResult, import_feed
from transit.models import Operator

logger = logging.getLogger(__name__)


def ensure_operators(codes, client: Client511) -> list[Operator]:
    """Operator rows for ``codes``, named from 511's operator list on first sight."""
    known = {op.code: op for op in Operator.objects.filter(code__in=codes)}
    missing = [code for code in codes if code not in known]
    if missing:
        listing = {item["Id"]: item for item in client.operators()}
        for code in missing:
            if code not in listing:
                raise ValueError(f"511 has no operator {code!r}")
            known[code] = Operator.objects.create(code=code, name=listing[code]["Name"])
    return [known[code] for code in codes]


def refresh(codes=None, client: Client511 | None = None) -> list[ImportResult]:
    client = client or Client511()
    codes = codes or settings.TRANSIT["OPERATORS"]
    results = []
    for operator in ensure_operators(codes, client):
        archive = client.static_feed(operator.code)
        results.append(import_feed(operator, archive, keep=settings.TRANSIT["KEEP_FEEDS"]))
    return results
