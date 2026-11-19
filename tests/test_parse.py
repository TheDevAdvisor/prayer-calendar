import copy

import pytest

from prayer_calendar.parse import ParseError, check_plausible, clean_calendar, extract_conf_data, to_days

from .conftest import FIXTURES

# Valeurs relevées à la main sur la page d'Ivry le 19/11/2026
KNOWN_2026 = {
    "2026-02-01": {"fajr": "06:51", "shuruq": "08:21", "dhuhr": "13:08", "asr": "15:22", "maghrib": "17:51", "isha": "19:21"},
    "2026-02-08": {"fajr": "06:40", "shuruq": "08:10", "maghrib": "18:03", "isha": "19:33"},
    "2026-03-28": {"fajr": "05:07", "shuruq": "06:37", "maghrib": "19:18", "isha": "20:48"},
    "2026-03-29": {"fajr": "06:05", "shuruq": "07:35", "maghrib": "20:20", "isha": "21:50"},
}


def test_extract_ignores_braces_inside_strings():
    page = (FIXTURES / "fake_page.html").read_text(encoding="utf-8")
    assert extract_conf_data(page) == {
        "name": "Mosquée {test}",
        "tricky": "fin d'objet }; puis { ouvert",
        "quote": 'il dit "}" puis \\',
        "nested": {"a": [1, 2, {"b": "}"}]},
        "calendar": [],
    }


def test_extract_leaves_strings_alone_when_json_is_already_valid():
    assert extract_conf_data('<script>let confData = {"s": "a, }"};</script>') == {"s": "a, }"}


@pytest.mark.parametrize(
    "page",
    [
        "<html></html>",
        "let confData = null;",
        'let confData = {"a": {"b": 1}',
        "let confData = {pas: du json};",
    ],
)
def test_extract_fails_loudly(page):
    with pytest.raises(ParseError):
        extract_conf_data(page)


def test_known_values_2026(days2026):
    for day, expected in KNOWN_2026.items():
        assert expected.items() <= days2026[day].items(), day


def test_feb_29_is_skipped_in_a_common_year(days2026):
    assert len(days2026) == 365
    assert "2026-02-29" not in days2026
    assert (min(days2026), max(days2026)) == ("2026-01-01", "2026-12-31")


def test_feb_29_is_kept_in_a_leap_year(months):
    assert len(to_days(months, 2028)) == 366


def _broken(ivry, mutate):
    raw = copy.deepcopy(ivry["calendar"])
    mutate(raw)
    return raw


@pytest.mark.parametrize(
    "mutate",
    [
        lambda raw: raw.pop(),  # 11 mois
        lambda raw: raw[0].update({"1": ["06:00"] * 5}),  # 5 horaires
        lambda raw: raw[0].update({"1": ["25:00"] * 6}),  # heure impossible
        lambda raw: raw[0].update({"1": ["6h00"] * 6}),  # format inconnu
        lambda raw: raw.__setitem__(3, []),  # mois qui n'est pas un dict
    ],
)
def test_clean_calendar_rejects_bad_tables(ivry, mutate):
    with pytest.raises(ParseError):
        clean_calendar(_broken(ivry, mutate))


def test_missing_days_are_detected(months):
    del months[5][15]
    with pytest.raises(ParseError):
        to_days(months, 2026)


def _shift(hhmm, delta):
    h, m = divmod(int(hhmm[:2]) * 60 + int(hhmm[3:]) + delta, 60)
    return f"{h % 24:02d}:{m:02d}"


def test_real_table_is_plausible_across_clock_changes(days2026):
    # Le tableau saute d'une heure les 29/03 et 25/10 : en UTC, rien ne bouge
    check_plausible(days2026, "Europe/Paris")


def test_gmp_december_jump_is_tolerated(days2026):
    # Vrai tableau GMP 2026 : au 1er décembre, Fajr recule de 14 min et Isha avance de 11 min
    for key in (k for k in days2026 if k >= "2026-12-01"):
        days2026[key]["fajr"] = _shift(days2026[key]["fajr"], -14)
        days2026[key]["isha"] = _shift(days2026[key]["isha"], 11)
    check_plausible(days2026, "Europe/Paris")


def test_isha_after_midnight_is_accepted(days2026):
    june = {k: days2026[k] for k in ("2026-06-20", "2026-06-21", "2026-06-22")}
    for key, isha in zip(june, ("23:58", "00:01", "00:03")):
        june[key]["isha"] = isha
    check_plausible(june, "Europe/Paris")


def _swap_maghrib_isha(days):
    t = days["2026-05-10"]
    t["maghrib"], t["isha"] = t["isha"], t["maghrib"]


@pytest.mark.parametrize(
    "mutate, message",
    [
        (_swap_maghrib_isha, "2026-05-10 : horaires dans le désordre"),
        # Isha saisi sur 12 h toute l'année (19:21 -> 07:21)
        (lambda days: [t.update(isha=_shift(t["isha"], -720)) for t in days.values()], "2026-01-01 : horaires dans le désordre"),
        # Un seul Asr décalé de 40 min
        (lambda days: days["2026-06-15"].update(asr=_shift(days["2026-06-15"]["asr"], 40)), "2026-06-15 : asr"),
        # Juillet resté à l'heure d'hiver
        (lambda days: [t.update({p: _shift(v, -60) for p, v in t.items()}) for k, t in days.items() if k[5:7] == "07"], "2026-07-01 : fajr"),
    ],
)
def test_implausible_tables_are_rejected(days2026, mutate, message):
    mutate(days2026)
    with pytest.raises(ParseError, match=message):
        check_plausible(days2026, "Europe/Paris")
