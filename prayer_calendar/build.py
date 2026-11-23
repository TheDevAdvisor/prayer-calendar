"""Construit les calendriers : python -m prayer_calendar.build [--config config.yaml]

Tout est calculé en mémoire avant d'écrire quoi que ce soit : si le téléchargement ou le
parsing d'une mosquée échoue, l'exécution sort en erreur et aucun fichier n'est touché.
"""

import argparse
import html
import json
import logging
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from string import Template
from urllib.parse import quote
from zoneinfo import ZoneInfo

import yaml

from . import fetch, ics, parse, ramadan, year

log = logging.getLogger("prayer_calendar")

# Le calendrier remonte à 9 semaines avant le lundi courant (63 à 69 jours). L'Action tourne tous
# les jours, mais tout est calé sur le lundi : sans correction de la mosquée, un commit par semaine.
WEEKS_BEFORE = 9
DEFAULT_TZ = "Europe/Paris"
TEMPLATES = Path(__file__).parent / "templates"
DEFAULTS = {
    "page_message": "",
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


def week_of(day):
    """Lundi de la semaine de `day`."""
    return day - timedelta(days=day.weekday())


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
    parse.check_plausible(snapshots[table_year], tz_name)
    all_days = {d: t for y in sorted(snapshots) for d, t in snapshots[y].items()}

    # Tableau de l'an dernier et rien de réel pour cette année : on prolonge sans rien enregistrer.
    # Dès que la mosquée publie, le vrai snapshot existe et le provisoire disparaît.
    provisional = table_year < today.year and today.year not in snapshots
    if provisional:
        log.warning(
            "%s : tableau %s pas encore publié, calendrier %s PROVISOIRE reporté depuis %s",
            slug,
            today.year,
            today.year,
            table_year,
        )
        all_days.update(year.provisional_days(months, table_year, today.year, tz_name))

    first = (week_of(today) - timedelta(weeks=WEEKS_BEFORE)).isoformat()
    days = {d: t for d, t in all_days.items() if d >= first}
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
        "provisional": provisional,
        "snapshots": sorted(snapshots),
        "events": len(events),
        "first_date": min(days),
        "last_date": max(days),
        "ramadan": [{"start": s.isoformat(), "end": e.isoformat()} for s, e in ramadan_used],
    }
    # Pour la page : les horaires à partir du lundi, que le navigateur affiche pour « aujourd'hui »
    week = week_of(today).isoformat()
    page = {
        "source": mosque.get("source_name") or conf.get("name") or slug,
        "url": mosque["url"],
        "tz": tz_name,
        "days": {d: [t[p] for p in parse.PRAYERS] for d, t in sorted(all_days.items()) if d >= week},
    }
    return files, status, today, page


def _template(name):
    return Template((TEMPLATES / name).read_text(encoding="utf-8"))


def _text(value):
    return html.escape(value, quote=False)


def _plain(title):
    """« 🕌 Fajr » -> « Fajr » : la page affiche les noms sans emoji."""
    return re.sub(r"^\W+", "", title).strip()


def _join_fr(words):
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " et " + words[-1]


def _alert_phrase(minutes_before):
    if not minutes_before:
        return ""
    moments = [
        "à l'heure de chaque prière" if n == 0 else f"{n} min avant"
        for n in sorted(set(minutes_before), reverse=True)
    ]
    return "avec une alerte " + _join_fr(moments)


def _features(cfg):
    names = _join_fr([_plain(cfg["titles"][p]) for p in cfg["prayers"]])
    alert = _alert_phrase(cfg["alarm_minutes_before"])
    items = [("🕌", "Les prières du jour", f"{names}, chaque jour{', ' + alert if alert else ''}.")]
    if cfg["friday_jumua"]:
        items.append((
            "🤲",
            "Jumu'a le vendredi",
            "Le vendredi, Dhuhr devient Jumu'a, à l'heure de Dhuhr. "
            "L'heure du prêche peut varier : vérifiez-la auprès de votre mosquée.",
        ))
    rcfg = cfg["ramadan"]
    if rcfg["enabled"]:
        items.append((
            "🌙",
            "Ramadan",
            f"Pendant le Ramadan, une alerte Imsak {rcfg['imsak_minutes_before_fajr']} min avant Fajr, "
            "et Maghrib devient l'Iftar.",
        ))
    always = "Les horaires se mettent à jour chaque semaine, sans rien refaire de votre côté."
    if cfg["transparent"]:
        always += " Les prières sont marquées « disponible » et ne bloquent pas votre agenda."
    items.append(("🔄", "Toujours à jour", always))
    return "\n".join(
        f'    <li><span class="icon" aria-hidden="true">{icon}</span>'
        f"<div><h3>{_text(title)}</h3><p>{_text(body)}</p></div></li>"
        for icon, title, body in items
    )


def _card(status, today, page, cfg, site_url):
    https_url = f"{site_url}/{status['ics'].removeprefix('docs/')}"
    webcal_url = "webcal://" + https_url.split("://", 1)[1]
    first, last = (date.fromisoformat(status[k]) for k in ("first_date", "last_date"))
    rcfg = cfg["ramadan"]
    labels = {p: _plain(t) for p, t in cfg["titles"].items()}
    labels |= {"imsak": _plain(rcfg["imsak_title"]), "iftar": _plain(rcfg["maghrib_title"])}
    data = {
        "tz": page["tz"],
        "order": list(parse.PRAYERS),
        "prayers": cfg["prayers"],
        "jumua": bool(cfg["friday_jumua"]),
        "imsak": rcfg["imsak_minutes_before_fajr"],
        "ramadan": [[r["start"], r["end"]] for r in status["ramadan"]],
        "labels": labels,
        "days": page["days"],
    }
    return _template("card.html").substitute(
        source=_text(page["source"]),
        first=f"{first:%d/%m/%Y}",
        last=f"{last:%d/%m/%Y}",
        week=f"{week_of(today):%d/%m/%Y}",
        webcal=html.escape(webcal_url),
        google=html.escape("https://calendar.google.com/calendar/r?cid=" + quote(webcal_url, safe="")),
        https=html.escape(https_url),
        times=json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/"),
    )


def render_index(entries, cfg):
    """Page d'abonnement : ce que contient le calendrier, d'où viennent les horaires, comment s'abonner.

    Le nom de la mosquée n'apparaît que sur cette page : le calendrier lui-même reste générique.
    """
    site_url = cfg["site_url"].rstrip("/")
    sources = [page["source"] for _, _, page in entries]
    names = _join_fr([_plain(cfg["titles"][p]) for p in cfg["prayers"]])
    alert = _alert_phrase(cfg["alarm_minutes_before"])
    links = _join_fr([f'<a href="{html.escape(p["url"])}">{_text(p["source"])}</a>' for _, _, p in entries])
    message = cfg["page_message"]
    return _template("index.html").substitute(
        title=_text("Horaires de prière" + (f" · {sources[0]}" if len(sources) == 1 else "")),
        description=html.escape(
            f"Horaires de prière ({' · '.join(sources)}) dans votre agenda : iPhone, Mac, Android, Outlook. "
            "Gratuit, mis à jour chaque semaine."
        ),
        page_url=html.escape(site_url + "/"),
        lead=_text(
            f"{names} s'ajoutent à votre calendrier{', ' + alert if alert else ''}. "
            "Vous vous abonnez une fois, et les horaires se mettent ensuite à jour tout seuls."
        ),
        cards="\n".join(_card(status, today, page, cfg, site_url) for status, today, page in entries),
        features=_features(cfg),
        message=f'<p class="message">{_text(message)}</p>' if message else "",
        fineprint=f"Source : {links}, via Mawaqit. En cas de doute, l'horaire affiché par votre mosquée fait foi.",
    )


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
            mosque_files, status, today, page = prepare(mosque, cfg, root, args.today)
        except Exception:
            log.exception("%s : échec, aucun fichier modifié", mosque.get("slug"))
            failed = True
            continue
        files.update(mosque_files)
        statuses[mosque["slug"]] = status
        entries.append((status, today, page))
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
    files[docs / "index.html"] = render_index(entries, cfg)
    files[docs / ".nojekyll"] = ""
    for path, content in files.items():
        if write_if_changed(path, content):
            log.info("Mis à jour : %s", path.relative_to(root))
    log.info("Exécution terminée le %s", datetime.now(ZoneInfo(DEFAULT_TZ)).isoformat("T", "seconds"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
