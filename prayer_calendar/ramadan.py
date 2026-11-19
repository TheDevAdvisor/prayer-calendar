"""Jours de Ramadan : calcul Umm al-Qura (hijridate) ou dates imposées dans la config."""

from datetime import date, timedelta

from hijridate import Gregorian


def normalize_overrides(raw):
    """{2027: {"start": "2027-02-08", "end": "2027-03-08"}} -> clés int, valeurs date."""
    out = {}
    for year, period in (raw or {}).items():
        start, end = (
            v if isinstance(v, date) else date.fromisoformat(str(v))
            for v in (period["start"], period["end"])
        )
        if end < start:
            raise ValueError(f"Ramadan {year} : la fin précède le début")
        out[int(year)] = {"start": start, "end": end}
    return out


def is_ramadan(day, adjustment=0, overrides=None):
    overrides = overrides or {}
    if any(o["start"] <= day <= o["end"] for o in overrides.values()):
        return True
    if day.year in overrides:  # l'année a des dates officielles : le calcul ne compte plus
        return False
    return Gregorian.fromdate(day + timedelta(days=adjustment)).to_hijri().month == 9


def ramadan_ranges(days, adjustment=0, overrides=None):
    """Regroupe les jours de Ramadan consécutifs en [(début, fin), ...]."""
    ranges = []
    for day in sorted(days):
        if not is_ramadan(day, adjustment, overrides):
            continue
        if ranges and ranges[-1][1] == day - timedelta(days=1):
            ranges[-1][1] = day
        else:
            ranges.append([day, day])
    return [tuple(r) for r in ranges]
