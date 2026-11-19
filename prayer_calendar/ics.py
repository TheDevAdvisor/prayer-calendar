"""Événements de prière et rendu ICS (horaires en UTC, sortie déterministe)."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from icalendar import Alarm, Calendar
from icalendar import Event as VEvent
from icalendar.prop import vInline

PRODID = "-//prayer-calendar//Mawaqit ICS//FR"


@dataclass(frozen=True)
class Event:
    day: date
    uid: str
    title: str
    start: datetime
    end: datetime
    alarms: tuple


def to_utc(day, hhmm, tz):
    h, m = map(int, hhmm.split(":"))
    return datetime.combine(day, time(h, m), tzinfo=tz).astimezone(UTC)


def make_events(slug, days, cfg, tz_name, ramadan_day):
    """days : {"AAAA-MM-JJ": {"fajr": "HH:MM", ...}}. ramadan_day : date -> bool."""
    tz = ZoneInfo(tz_name)
    duration = timedelta(minutes=cfg["event_duration_minutes"])
    rcfg = cfg["ramadan"]
    events = []

    def add(day, name, title, start, end, alarms):
        uid = f"{slug}-{day:%Y%m%d}-{name}@prayer-calendar"
        events.append(Event(day, uid, title, start, end, tuple(alarms or ())))

    for iso, times in days.items():
        day = date.fromisoformat(iso)
        ramadan = rcfg["enabled"] and ramadan_day(day)
        if ramadan:
            fajr = to_utc(day, times["fajr"], tz)
            imsak = fajr - timedelta(minutes=rcfg["imsak_minutes_before_fajr"])
            add(day, "imsak", rcfg["imsak_title"], imsak, fajr, rcfg["imsak_alarm_minutes_before"])
        for prayer in cfg["prayers"]:
            start = to_utc(day, times[prayer], tz)
            title = cfg["titles"][prayer]
            if ramadan and prayer == "maghrib":
                title = rcfg["maghrib_title"]
            add(day, prayer, title, start, start + duration, cfg["alarm_minutes_before"])

    return sorted(events, key=lambda e: (e.start, e.uid))


def _trigger(minutes_before):
    # -PT10M = 10 min avant, PT0M = à l'heure pile
    return vInline(f"-PT{minutes_before}M" if minutes_before > 0 else f"PT{-minutes_before}M")


def render(events, name, tz_name, cfg):
    cal = Calendar()
    cal.add("prodid", PRODID)
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", name)
    cal.add("x-wr-timezone", tz_name)
    cal.add("refresh-interval", timedelta(hours=12), parameters={"VALUE": "DURATION"})
    cal.add("x-published-ttl", "PT12H")

    for ev in events:
        vevent = VEvent()
        vevent.add("uid", ev.uid)
        # DTSTAMP tiré des données, jamais de « maintenant » : même entrée, même fichier
        vevent.add("dtstamp", datetime.combine(ev.day, time(0), tzinfo=UTC))
        vevent.add("dtstart", ev.start)
        vevent.add("dtend", ev.end)
        vevent.add("summary", ev.title)
        vevent.add("transp", "TRANSPARENT" if cfg["transparent"] else "OPAQUE")
        if cfg.get("location"):
            vevent.add("location", cfg["location"])
        if cfg.get("description"):
            vevent.add("description", cfg["description"])
        for minutes_before in ev.alarms:
            alarm = Alarm()
            alarm.add("action", "DISPLAY")
            alarm.add("description", ev.title)
            alarm.add("trigger", _trigger(minutes_before))
            vevent.add_component(alarm)
        cal.add_component(vevent)

    return cal.to_ical()
