"""Téléchargement de la page publique Mawaqit d'une mosquée."""

import logging
import time

import requests

log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9",
}
TIMEOUT = 30
RETRIES = 2


def fetch_page(url, session=None, sleep=time.sleep):
    """Renvoie le HTML de la page. Au plus RETRIES nouvelles tentatives, puis l'erreur remonte."""
    http = session or requests.Session()
    for attempt in range(RETRIES + 1):
        try:
            response = http.get(url, headers=HEADERS, timeout=TIMEOUT)
            response.raise_for_status()
            return response.content.decode("utf-8")
        except requests.RequestException as exc:
            if attempt == RETRIES:
                raise
            delay = 5 * 2**attempt
            log.warning("Téléchargement de %s raté (%s), nouvel essai dans %s s", url, exc, delay)
            sleep(delay)
