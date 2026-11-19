from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from icalendar import Calendar

from prayer_calendar.ics import make_events, render, to_utc

SLUG = "annour-ivry-sur-seine"
TZ = "Europe/Paris"
NAME = "🕌 Prières – Annour Ivry"


def test_to_utc_across_dst_changes():
    paris = ZoneInfo(TZ)
    assert to_utc(date(2026, 3, 28), "05:07", paris) == datetime(2026, 3, 28, 4, 7, tzinfo=UTC)
    assert to_utc(date(2026, 3, 29), "06:05", paris) == datetime(2026, 3, 29, 4, 5, tzinfo=UTC)
    assert to_utc(date(2026, 10, 24), "07:00", paris) == datetime(2026, 10, 24, 5, 0, tzinfo=UTC)
    assert to_utc(date(2026, 10, 25), "07:00", paris) == datetime(2026, 10, 25, 6, 0, tzinfo=UTC)


def test_regular_day(cfg, days2026):
    events = make_events(SLUG, {"2026-02-01": days2026["2026-02-01"]}, cfg, TZ, lambda d: False)
    assert [e.uid for e in events] == [
        f"{SLUG}-20260201-{p}@prayer-calendar" for p in ("fajr", "dhuhr", "asr", "maghrib", "isha")
    ]
    fajr = events[0]
    assert fajr.title == "🕌 Fajr"
    assert fajr.start == datetime(2026, 2, 1, 5, 51, tzinfo=UTC)
    assert fajr.end - fajr.start == timedelta(minutes=10)
    assert fajr.alarms == (0,)


def test_ramadan_day_adds_imsak_and_renames_maghrib(cfg, days2026):
    events = make_events(SLUG, {"2026-03-01": days2026["2026-03-01"]}, cfg, TZ, lambda d: True)
    by_name = {e.uid.split("@")[0].rsplit("-", 1)[1]: e for e in events}
    assert list(by_name) == ["imsak", "fajr", "dhuhr", "asr", "maghrib", "isha"]
    assert by_name["imsak"].title == "🌙 Imsak"
    assert by_name["imsak"].end == by_name["fajr"].start
    assert by_name["fajr"].start - by_name["imsak"].start == timedelta(minutes=10)
    assert by_name["fajr"].title == "🕌 Fajr"
    assert by_name["maghrib"].title == "🌙 Iftar – Maghrib"


def test_friday_dhuhr_becomes_jumua_at_the_same_time(cfg, days2026):
    friday = "2026-02-06"
    events = make_events(SLUG, {friday: days2026[friday]}, cfg, TZ, lambda d: False)
    jumua = events[1]
    assert jumua.uid == f"{SLUG}-20260206-jumua@prayer-calendar"
    assert jumua.title == "🕌 Jumu'a"
    assert jumua.start == to_utc(date(2026, 2, 6), days2026[friday]["dhuhr"], ZoneInfo(TZ))
    assert not any("-dhuhr@" in e.uid for e in events)

    cfg["friday_jumua"] = False
    events = make_events(SLUG, {friday: days2026[friday]}, cfg, TZ, lambda d: False)
    assert events[1].title == "🕌 Dhuhr"


def test_ramadan_can_be_disabled(cfg, days2026):
    cfg["ramadan"]["enabled"] = False
    events = make_events(SLUG, {"2026-03-01": days2026["2026-03-01"]}, cfg, TZ, lambda d: True)
    assert len(events) == 5


def test_shuruq_is_optional_and_events_stay_in_time_order(cfg, days2026):
    cfg["prayers"] = ["fajr", "dhuhr", "asr", "maghrib", "isha", "shuruq"]
    events = make_events(SLUG, {"2026-02-01": days2026["2026-02-01"]}, cfg, TZ, lambda d: False)
    assert [e.title for e in events][:3] == ["🕌 Fajr", "☀️ Chourouq", "🕌 Dhuhr"]


def _render(cfg, days2026, dates=("2026-02-01", "2026-02-02")):
    days = {d: days2026[d] for d in dates}
    return render(make_events(SLUG, days, cfg, TZ, lambda d: False), NAME, TZ, cfg)


def test_ics_header_and_events(cfg, days2026):
    data = _render(cfg, days2026)
    lines = data.decode().splitlines()
    for expected in [
        "VERSION:2.0",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{NAME}",
        "X-WR-TIMEZONE:Europe/Paris",
        "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
        "X-PUBLISHED-TTL:PT12H",
        f"UID:{SLUG}-20260201-fajr@prayer-calendar",
        "DTSTART:20260201T055100Z",
        "DTEND:20260201T060100Z",
        "DTSTAMP:20260201T000000Z",
        "TRANSP:TRANSPARENT",
        "TRIGGER:PT0M",
    ]:
        assert expected in lines, expected

    cal = Calendar.from_ical(data)
    events = cal.walk("VEVENT")
    assert len(events) == 10
    for event in events:
        assert "LOCATION" not in event and "DESCRIPTION" not in event
        (alarm,) = event.walk("VALARM")
        assert alarm["ACTION"] == "DISPLAY"
        assert alarm["DESCRIPTION"] == event["SUMMARY"]


def test_ics_is_deterministic(cfg, days2026):
    assert _render(cfg, days2026) == _render(cfg, days2026)


def test_ics_options(cfg, days2026):
    cfg.update(transparent=False, location="Ivry", description="Horaires Mawaqit", alarm_minutes_before=[15, 0])
    text = _render(cfg, days2026, dates=("2026-02-01",)).decode()
    assert "TRANSP:OPAQUE" in text
    assert "LOCATION:Ivry" in text and "DESCRIPTION:Horaires Mawaqit" in text
    assert "TRIGGER:-PT15M" in text and "TRIGGER:PT0M" in text

    cfg["alarm_minutes_before"] = []
    assert "VALARM" not in _render(cfg, days2026, dates=("2026-02-01",)).decode()
