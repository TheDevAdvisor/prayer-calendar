"""Extraction de `let confData = {...};` et normalisation du tableau annuel."""

import calendar
import json
import re
from datetime import date

PRAYERS = ("fajr", "shuruq", "dhuhr", "asr", "maghrib", "isha")

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
