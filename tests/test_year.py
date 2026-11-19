from datetime import date

from prayer_calendar.parse import PRAYERS, minutes
from prayer_calendar.year import detect_year, dst_jump_day, last_sunday_of_march, provisional_days

TZ = "Europe/Paris"


def test_last_sunday_of_march():
    assert [last_sunday_of_march(y) for y in (2026, 2027, 2028, 2030)] == [29, 28, 26, 31]


def test_dst_jump_is_on_march_29(months):
    assert dst_jump_day(months) == 29


def test_table_year_is_current_year(months):
    assert detect_year(months, date(2026, 11, 19)) == 2026


def test_table_published_early_for_next_year(months):
    assert detect_year(months, date(2025, 12, 20)) == 2026


def test_table_from_last_year_is_recognised(months):
    assert detect_year(months, date(2027, 1, 2)) == 2026


def test_unknown_year_falls_back_to_current_with_warning(months, caplog):
    assert detect_year(months, date(2028, 6, 1)) == 2028
    assert "introuvable" in caplog.text


def test_provisional_days_move_dst_to_the_right_day(months):
    prov = provisional_days(months, 2026, 2027, TZ)
    assert len(prov) == 365
    # 27/03 : heure d'hiver les deux années, rien ne bouge
    assert prov["2027-03-27"] == dict(zip(PRAYERS, months[2][27]))
    # 28/03/2027 : déjà l'heure d'été (en 2026, elle n'arrivait que le 29).
    # 05:07 CET en 2026 = 04:07 UTC, reporté en 2027 : 06:07 CEST, à 2 min du premier Fajr d'été (06:05)
    assert prov["2027-03-28"]["fajr"] == "06:07"
    assert abs(minutes(prov["2027-03-28"]["fajr"]) - minutes(months[2][29][0])) <= 2
    # Du 25 au 30/10/2027, encore l'heure d'été (fin le 31 en 2027, le 25 en 2026)
    assert minutes(prov["2027-10-30"]["fajr"]) == minutes(months[9][30][0]) + 60
    assert prov["2027-10-31"] == dict(zip(PRAYERS, months[9][31]))


def test_provisional_leap_year_gets_february_29(months):
    prov = provisional_days(months, 2027, 2028, TZ)
    assert len(prov) == 366
    assert prov["2028-02-29"] == dict(zip(PRAYERS, months[1][29]))
