"""Construit les calendriers : python -m prayer_calendar.build [--config config.yaml]

Tout est calculé en mémoire avant d'écrire quoi que ce soit : si le téléchargement ou le
parsing d'une mosquée échoue, l'exécution sort en erreur et aucun fichier n'est touché.
"""

import argparse
import html
import json
import logging
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from . import fetch, ics, parse, ramadan, year

log = logging.getLogger("prayer_calendar")

DAYS_BEFORE_TODAY = 60
DEFAULT_TZ = "Europe/Paris"
DEFAULTS = {
    "prayers": ["fajr", "dhuhr", "asr", "maghrib", "isha"],
    "friday_jumua": True,
    "titles": {
        "fajr": "🕌 Fajr",
        "shuruq": "☀️ Chourouq",
        "dhuhr": "🕌 Dhuhr",
        "jumua": "🕌 Jumu'a",
        "asr": "🕌 Asr",
        "maghrib": "🕌 Maghrib",
        "isha": "🕌 Isha",
    },
    "event_duration_minutes": 10,
    "transparent": True,
    "location": None,
    "description": "",
    "alarm_minutes_before": [0],
    "ramadan": {
        "enabled": True,
        "imsak_minutes_before_fajr": 10,
        "imsak_title": "🌙 Imsak",
        "imsak_alarm_minutes_before": [0],
        "maghrib_title": "🌙 Iftar – Maghrib",
        "hijri_adjustment": None,
        "overrides": {},
    },
}


def load_config(path):
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    cfg = {**DEFAULTS, **raw}
    cfg["titles"] = {**DEFAULTS["titles"], **(raw.get("titles") or {})}
    cfg["ramadan"] = {**DEFAULTS["ramadan"], **(raw.get("ramadan") or {})}
    cfg["ramadan"]["overrides"] = ramadan.normalize_overrides(cfg["ramadan"]["overrides"])
    if not cfg.get("site_url"):
        raise ValueError("config : « site_url » manquant")
    if not cfg.get("mosques"):
        raise ValueError("config : aucune mosquée dans « mosques »")
    unknown = set(cfg["prayers"]) - set(parse.PRAYERS)
    if unknown:
        raise ValueError(f"config : prières inconnues {sorted(unknown)}")
    for mosque in cfg["mosques"]:
        if not (mosque["output"].startswith("docs/") and mosque["output"].endswith(".ics")):
            raise ValueError(f"config : {mosque['output']} doit être un .ics dans docs/")
    return cfg


def load_snapshots(folder):
    """{année: {"AAAA-MM-JJ": {...}}} depuis data/<slug>/<année>.json."""
    return {
        int(path.stem): json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(folder.glob("[0-9][0-9][0-9][0-9].json"))
    }


def snapshot_text(days):
    """Une ligne par jour : les diffs Git restent lisibles quand la mosquée corrige un horaire."""
    lines = ",\n".join(f"  {json.dumps(d)}: {json.dumps(t)}" for d, t in days.items())
    return "{\n" + lines + "\n}\n"


def prepare(mosque, cfg, root, today=None):
    """Télécharge, analyse et calcule tout pour une mosquée. N'écrit rien."""
    slug = mosque["slug"]
    conf = parse.extract_conf_data(fetch.fetch_page(mosque["url"]))
    months = parse.clean_calendar(conf.get("calendar"))
    tz_name = conf.get("timezone") or DEFAULT_TZ
    today = today or datetime.now(ZoneInfo(tz_name)).date()
    table_year = year.detect_year(months, today)

    folder = root / "data" / slug
    snapshots = load_snapshots(folder)
    snapshots[table_year] = parse.to_days(months, table_year)

    first = (today - timedelta(days=DAYS_BEFORE_TODAY)).isoformat()
    days = {d: t for y in sorted(snapshots) for d, t in snapshots[y].items() if d >= first}
    if not days:
        raise ValueError(f"{slug} : aucun horaire publié après le {first}, rien à servir")

    rcfg = cfg["ramadan"]
    adjustment = rcfg["hijri_adjustment"]
    if adjustment is None:
        adjustment = int(conf.get("hijriAdjustment") or 0)

    def ramadan_day(d):
        return ramadan.is_ramadan(d, adjustment, rcfg["overrides"])

    events = ics.make_events(mosque.get("uid_prefix") or slug, days, cfg, tz_name, ramadan_day)
    calendar_name = mosque.get("calendar_name") or conf.get("name") or slug
    ramadan_used = []
    if rcfg["enabled"]:
        dates = [date.fromisoformat(d) for d in days]
        ramadan_used = ramadan.ramadan_ranges(dates, adjustment, rcfg["overrides"])

    files = {
        folder / f"{table_year}.json": snapshot_text(snapshots[table_year]),
        root / mosque["output"]: ics.render(events, calendar_name, tz_name, cfg),
    }
    status = {
        "name": conf.get("name"),
        "calendar_name": calendar_name,
        "ics": mosque["output"],
        "table_year": table_year,
        "snapshots": sorted(snapshots),
        "events": len(events),
        "first_date": min(days),
        "last_date": max(days),
        "ramadan": [{"start": s.isoformat(), "end": e.isoformat()} for s, e in ramadan_used],
    }
    return files, status, today


def render_index(entries, site_url):
    """Page d'abonnement. Volontairement sans nom de mosquée : seul le nom du calendrier apparaît."""
    names = html.escape(" · ".join(status["calendar_name"] for status, _ in entries))
    sections = []
    for status, today in entries:
        https_url = f"{site_url.rstrip('/')}/{status['ics'].removeprefix('docs/')}"
        webcal_url = "webcal://" + https_url.split("://", 1)[1]
        first, last = (date.fromisoformat(status[k]) for k in ("first_date", "last_date"))
        heading = f"<h2>{html.escape(status['calendar_name'])}</h2>\n" if len(entries) > 1 else ""
        sections.append(
            f"""<section>
{heading}<p>Horaires du {first:%d/%m/%Y} au {last:%d/%m/%Y}. Dernière mise à jour : {today:%d/%m/%Y}.</p>
<p><a class="button" href="{html.escape(webcal_url)}">S'abonner</a></p>
<p>Lien https : <a href="{html.escape(https_url)}">{html.escape(https_url)}</a></p>
</section>"""
        )
    body = "\n".join(sections)
    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{names}</title>
<style>
:root {{ color-scheme: light dark; }}
body {{ font-family: system-ui, sans-serif; max-width: 36rem; margin: 2rem auto; padding: 0 1rem; line-height: 1.5; }}
a.button {{ display: inline-block; padding: .6rem 1.2rem; border-radius: .5rem; background: #0a7d4f; color: #fff; text-decoration: none; }}
.source {{ font-size: .85rem; opacity: .7; }}
</style>
</head>
<body>
<h1>{names}</h1>
{body}
<p class="source">Horaires : Mawaqit</p>
</body>
</html>
"""


def write_if_changed(path, content):
    data = content.encode("utf-8") if isinstance(content, str) else content
    if path.exists() and path.read_bytes() == data:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)
    return True


class _Formatter(logging.Formatter):
    """Dans GitHub Actions, avertissements et erreurs deviennent des annotations du run."""

    def format(self, record):
        text = super().format(record)
        if os.environ.get("GITHUB_ACTIONS") == "true" and record.levelno >= logging.WARNING:
            return f"::{'error' if record.levelno >= logging.ERROR else 'warning'}::{text}"
        return text


def main(argv=None):
    parser = argparse.ArgumentParser(description="Génère les calendriers ICS depuis Mawaqit.")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--today", type=date.fromisoformat, help="date de référence AAAA-MM-JJ")
    args = parser.parse_args(argv)

    handler = logging.StreamHandler()
    handler.setFormatter(_Formatter("%(levelname)s %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])

    config_path = Path(args.config).resolve()
    root = config_path.parent
    cfg = load_config(config_path)

    files, statuses, entries, failed = {}, {}, [], False
    for mosque in cfg["mosques"]:
        try:
            mosque_files, status, today = prepare(mosque, cfg, root, args.today)
        except Exception:
            log.exception("%s : échec, aucun fichier modifié", mosque.get("slug"))
            failed = True
            continue
        files.update(mosque_files)
        statuses[mosque["slug"]] = status
        entries.append((status, today))
        log.info(
            "%s : tableau %s, %s événements du %s au %s, Ramadan %s",
            mosque["slug"],
            status["table_year"],
            status["events"],
            status["first_date"],
            status["last_date"],
            status["ramadan"] or "hors période",
        )
    if failed:
        return 1

    docs = root / "docs"
    files[docs / "status.json"] = json.dumps(statuses, indent=2, ensure_ascii=False) + "\n"
    files[docs / "index.html"] = render_index(entries, cfg["site_url"])
    files[docs / ".nojekyll"] = ""
    for path, content in files.items():
        if write_if_changed(path, content):
            log.info("Mis à jour : %s", path.relative_to(root))
    log.info("Exécution terminée le %s", datetime.now(ZoneInfo(DEFAULT_TZ)).isoformat("T", "seconds"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
