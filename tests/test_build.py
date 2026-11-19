import copy
import json
import shutil
from pathlib import Path

import pytest
import requests
from icalendar import Calendar

from prayer_calendar import build, fetch

ROOT = Path(__file__).resolve().parent.parent
URL = "https://mawaqit.net/fr/annour-ivry-sur-seine"
SLUG = "annour-ivry-sur-seine"


def page(conf):
    return f"<html><script>\n    let confData = {json.dumps(conf)};\n    let lang = 'fr';\n</script></html>"


def table_2027(ivry):
    """Le tableau 2026 avec le passage à l'heure d'été déplacé au 28 mars (dernier dimanche de 2027)."""
    conf = copy.deepcopy(ivry)
    conf["calendar"][2]["28"] = conf["calendar"][2]["29"]
    return conf


@pytest.fixture
def project(tmp_path):
    shutil.copy(ROOT / "config.yaml", tmp_path / "config.yaml")
    return tmp_path


@pytest.fixture
def serve(monkeypatch):
    pages = {}

    def fake_fetch(url):
        if isinstance(pages[url], Exception):
            raise pages[url]
        return pages[url]

    monkeypatch.setattr(fetch, "fetch_page", fake_fetch)
    return pages


def run(project, today):
    return build.main(["--config", str(project / "config.yaml"), "--today", today])


def snapshot_of(project):
    return {p.relative_to(project): p.read_bytes() for p in project.rglob("*") if p.is_file()}


def events_of(project):
    return Calendar.from_ical((project / "docs/ivry.ics").read_bytes()).walk("VEVENT")


def test_full_run(project, serve, ivry):
    serve[URL] = page(ivry)
    assert run(project, "2026-11-19") == 0

    snapshot = json.loads((project / f"data/{SLUG}/2026.json").read_text())
    assert len(snapshot) == 365
    assert snapshot["2026-02-01"]["fajr"] == "06:51"

    # du 20/09 (J-60) au 31/12 : 103 jours x 5 prières, pas de Ramadan
    assert len(events_of(project)) == 515
    status = json.loads((project / "docs/status.json").read_text())[SLUG]
    assert status["table_year"] == 2026
    assert status["events"] == 515
    assert (status["first_date"], status["last_date"]) == ("2026-09-20", "2026-12-31")
    assert status["ramadan"] == []

    index = (project / "docs/index.html").read_text()
    assert 'href="webcal://thedevadvisor.github.io/prayer-calendar/ivry.ics"' in index
    assert "S'abonner" in index
    assert (project / "docs/.nojekyll").exists()


def test_same_data_gives_identical_files(project, serve, ivry):
    serve[URL] = page(ivry)
    run(project, "2026-11-19")
    before = snapshot_of(project)
    run(project, "2026-11-19")
    assert snapshot_of(project) == before


@pytest.mark.parametrize(
    "broken", [requests.ConnectionError("Mawaqit injoignable"), "<html>page refaite</html>"]
)
def test_failure_overwrites_nothing(project, serve, ivry, broken):
    serve[URL] = page(ivry)
    run(project, "2026-11-19")
    before = snapshot_of(project)

    serve[URL] = broken
    assert run(project, "2026-11-26") == 1
    assert snapshot_of(project) == before


def test_new_year_table_is_added_without_dropping_the_current_one(project, serve, ivry):
    serve[URL] = page(ivry)
    run(project, "2026-12-20")
    snapshot_2026 = (project / f"data/{SLUG}/2026.json").read_bytes()

    serve[URL] = page(table_2027(ivry))
    assert run(project, "2026-12-21") == 0
    assert (project / f"data/{SLUG}/2026.json").read_bytes() == snapshot_2026
    assert (project / f"data/{SLUG}/2027.json").exists()

    status = json.loads((project / "docs/status.json").read_text())[SLUG]
    assert status["table_year"] == 2027
    assert status["snapshots"] == [2026, 2027]
    assert (status["first_date"], status["last_date"]) == ("2026-10-22", "2027-12-31")
    assert status["ramadan"] == [{"start": "2027-02-08", "end": "2027-03-08"}]

    uids = {str(e["UID"]) for e in events_of(project)}
    assert f"{SLUG}-20261231-isha@prayer-calendar" in uids
    assert f"{SLUG}-20270208-imsak@prayer-calendar" in uids
    assert f"{SLUG}-20270207-imsak@prayer-calendar" not in uids
    # 436 jours x 5 + 29 Imsak
    assert len(uids) == 436 * 5 + 29
