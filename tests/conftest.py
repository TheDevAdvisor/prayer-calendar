import copy
import json
from pathlib import Path

import pytest

from prayer_calendar import build, parse

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def ivry():
    """Extrait de confData d'Annour Ivry (tableau 2026, relevé le 19/11/2026)."""
    return json.loads((FIXTURES / "ivry_2026.json").read_text(encoding="utf-8"))


@pytest.fixture
def months(ivry):
    return parse.clean_calendar(ivry["calendar"])


@pytest.fixture
def days2026(months):
    return parse.to_days(months, 2026)


@pytest.fixture
def cfg():
    return copy.deepcopy(build.DEFAULTS)
