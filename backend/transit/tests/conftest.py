import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from transit.gtfs.importer import import_feed
from transit.models import Operator

MINI = Path(__file__).parent / "fixtures" / "mini"
REGIONAL = MINI.parent / "regional"
TZ = ZoneInfo("America/Los_Angeles")


def local(*args):
    return datetime(*args, tzinfo=TZ)


@pytest.fixture
def operator(db):
    return Operator.objects.create(code="TT", name="")


@pytest.fixture
def feed(operator):
    return import_feed(operator, MINI).feed


@pytest.fixture
def gtfs_dir(tmp_path):
    """A writable copy of the mini feed, for tests that break it on purpose."""
    target = tmp_path / "gtfs"
    shutil.copytree(MINI, target)
    return target
