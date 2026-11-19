import copy

import pytest

from prayer_calendar.parse import ParseError, clean_calendar, extract_conf_data, to_days

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
