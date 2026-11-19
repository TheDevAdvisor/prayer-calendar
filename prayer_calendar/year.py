"""Année du tableau, déduite du passage à l'heure d'été (le tableau Mawaqit ne la donne pas)."""

import logging
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .parse import PRAYERS, minutes

log = logging.getLogger(__name__)

MARCH = 2  # index dans la liste des mois
SHURUQ = 1  # index dans la liste des horaires


def last_sunday_of_march(year):
    end = date(year, 3, 31)
    return (end - timedelta(days=(end.weekday() - 6) % 7)).day


def dst_jump_day(months):
    """Jour de mars où le Chourouq avance d'environ une heure sur la veille, sinon None."""
    march = months[MARCH]
    jumps = [
        day
        for day in range(2, 32)
        if day in march
        and day - 1 in march
        and 45 <= minutes(march[day][SHURUQ]) - minutes(march[day - 1][SHURUQ]) <= 75
    ]
    return jumps[0] if len(jumps) == 1 else None


def detect_year(months, today):
    day = dst_jump_day(months)
    # Trois années consécutives ont toujours des derniers dimanches de mars différents
    for year in (today.year - 1, today.year, today.year + 1):
        if day == last_sunday_of_march(year):
            return year
    log.warning(
        "Année du tableau introuvable (saut d'heure d'été au %s mars) : on prend %s par défaut",
        day,
        today.year,
    )
    return today.year


def provisional_days(months, table_year, year, tz_name):
    """Horaires PROVISOIRES de `year` tirés du tableau de `table_year`.

    Chaque horaire est converti en UTC à sa date d'origine, puis ce même instant UTC est
    reporté au même jour de `year` : le changement d'heure tombe ainsi au bon jour.
    """
    tz = ZoneInfo(tz_name)
    days = {}
    for m, month in enumerate(months, start=1):
        for d, times in sorted(month.items()):
            try:
                target = date(year, m, d)
            except ValueError:
                continue
            try:
                source = date(table_year, m, d)
            except ValueError:  # 29 février absent de l'année du tableau : même heure d'hiver que la veille
                source = date(table_year, m, d - 1)
            days[target.isoformat()] = {
                prayer: _carry(hhmm, source, target, tz) for prayer, hhmm in zip(PRAYERS, times)
            }
    return days


def _carry(hhmm, source, target, tz):
    instant = datetime.combine(source, time.fromisoformat(hhmm), tzinfo=tz).astimezone(UTC)
    return f"{(instant + (target - source)).astimezone(tz):%H:%M}"
