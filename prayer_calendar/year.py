"""Année du tableau, déduite du passage à l'heure d'été (le tableau Mawaqit ne la donne pas)."""

import logging
from datetime import date, timedelta

from .parse import minutes

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
    for year in (today.year, today.year + 1):
        if day == last_sunday_of_march(year):
            return year
    log.warning(
        "Année du tableau introuvable (saut d'heure d'été au %s mars) : on prend %s par défaut",
        day,
        today.year,
    )
    return today.year
