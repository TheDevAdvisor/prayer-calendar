import pytest
import requests

from prayer_calendar.fetch import fetch_page


class FakeResponse:
    def __init__(self, status, body=b""):
        self.status_code, self.content = status, body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, *outcomes):
        self.outcomes, self.calls = list(outcomes), []

    def get(self, url, headers, timeout):
        self.calls.append({"url": url, "headers": headers, "timeout": timeout})
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def test_retries_then_succeeds():
    session, sleeps = FakeSession(requests.ConnectionError("coupé"), FakeResponse(200, "Mosquée".encode())), []
    assert fetch_page("https://mawaqit.net/fr/x", session, sleeps.append) == "Mosquée"
    assert len(session.calls) == 2 and sleeps == [5]
    call = session.calls[0]
    assert call["timeout"] == 30
    assert call["headers"]["User-Agent"].startswith("Mozilla/5.0")
    assert call["headers"]["Accept-Language"].startswith("fr-FR")


def test_gives_up_after_two_retries():
    session, sleeps = FakeSession(FakeResponse(503), FakeResponse(503), FakeResponse(503), FakeResponse(200)), []
    with pytest.raises(requests.HTTPError):
        fetch_page("https://mawaqit.net/fr/x", session, sleeps.append)
    assert len(session.calls) == 3 and sleeps == [5, 10]
