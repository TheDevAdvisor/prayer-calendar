"""Extraction de `let confData = {...};` et normalisation du tableau annuel."""

import calendar
import json
import re
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

PRAYERS = ("fajr", "shuruq", "dhuhr", "asr", "maghrib", "isha")

# Plus gros écart toléré d'un jour à l'autre, mesuré en UTC pour ignorer les changements d'heure.
# Un vrai tableau bouge de 1 à 3 min par jour, mais celui de la GMP change de convention au
# 1er décembre 2026 (Fajr recule de 14 min, Isha avance de 11 min) : il faut de la marge.
MAX_DAILY_SHIFT = 30

_MARKER = re.compile(r"\blet\s+confData\s*=\s*(?=\{)")
_TIME = re.compile(r"^(\d{1,2}):(\d{2})$")


class ParseError(ValueError):
    pass


def extract_conf_data(html):
    """Lit l'objet confData par comptage d'accolades, en ignorant celles des chaînes."""
    match = _MARKER.search(html)
    if not match:
        raise ParseError("« let confData = { » introuvable dans la page")
    start = match.end()
    depth, quote, escaped = 0, None, False
    for i in range(start, len(html)):
        c = html[i]
        if quote:
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == quote:
                quote = None
        elif c in "\"'`":
            quote = c
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return _loads(html[start : i + 1])
    raise ParseError("Objet confData jamais refermé")


def _loads(text):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    try:  # syntaxe JS tolérée : virgules finales
        return json.loads(re.sub(r",\s*([}\]])", r"\1", text))
    except json.JSONDecodeError as exc:
        raise ParseError(f"confData n'est pas du JSON valide : {exc}") from exc


def minutes(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _hhmm(value, where):
    match = _TIME.match(value) if isinstance(value, str) else None
    if not match or int(match[1]) > 23 or int(match[2]) > 59:
        raise ParseError(f"{where} : horaire invalide {value!r}")
    return f"{int(match[1]):02d}:{match[2]}"


def clean_calendar(raw):
    """Valide `confData["calendar"]` : 12 mois de {jour: [6 horaires HH:MM]}."""
    if not isinstance(raw, list) or len(raw) != 12:
        raise ParseError("« calendar » doit être une liste de 12 mois")
    months = []
    for m, entries in enumerate(raw, start=1):
        if not isinstance(entries, dict) or not entries:
            raise ParseError(f"Mois {m} : format inattendu")
        month = {}
        for day, times in entries.items():
            where = f"{day}/{m}"
            if not str(day).isdigit() or not isinstance(times, list) or len(times) != len(PRAYERS):
                raise ParseError(f"{where} : entrée invalide {times!r}")
            month[int(day)] = [_hhmm(t, where) for t in times]
        months.append(month)
    return months


def to_days(months, year):
    """{"AAAA-MM-JJ": {"fajr": "HH:MM", ...}} pour l'année donnée, dates invalides ignorées."""
    days = {}
    for m, month in enumerate(months, start=1):
        for day, times in sorted(month.items()):
            try:
                d = date(year, m, day)
            except ValueError:  # Mawaqit garde un 29 février même les années non bissextiles
                continue
            days[d.isoformat()] = dict(zip(PRAYERS, times))
    expected = 366 if calendar.isleap(year) else 365
    if len(days) != expected:
        raise ParseError(f"{len(days)} jours valides pour {year}, {expected} attendus")
    return days


def check_plausible(days, tz_name):
    """Refuse un tableau bien formé mais incohérent, avant qu'il n'écrase le bon snapshot.

    Chaque jour, les six horaires se suivent dans l'ordre, et aucun ne bouge de plus de
    MAX_DAILY_SHIFT minutes sur la veille. Ça attrape les colonnes décalées, les horaires
    saisis sur 12 h, un mois recopié ou resté à la mauvaise heure.
    """
    tz = ZoneInfo(tz_name)
    previous = None
    for key, times in days.items():
        local = [minutes(times[p]) for p in PRAYERS]
        if local[-1] < 3 * 60:  # Isha après minuit, possible l'été sous de hautes latitudes
            local[-1] += 24 * 60
        if any(a >= b for a, b in zip(local, local[1:])):
            raise ParseError(f"{key} : horaires dans le désordre {times}")
        day = date.fromisoformat(key)
        local_midnight = datetime.combine(day, time(), tzinfo=tz)
        utc_midnight = datetime.combine(day, time(), tzinfo=UTC)
        utc = [(local_midnight + timedelta(minutes=m) - utc_midnight) / timedelta(minutes=1) for m in local]
        if previous:
            for prayer, before, now in zip(PRAYERS, previous, utc):
                if abs(now - before) > MAX_DAILY_SHIFT:
                    raise ParseError(
                        f"{key} : {prayer} à {times[prayer]} bouge de {now - before:+.0f} min "
                        f"sur la veille (max {MAX_DAILY_SHIFT})"
                    )
        previous = utc
