from datetime import date

from prayer_calendar.year import detect_year, dst_jump_day, last_sunday_of_march


def test_last_sunday_of_march():
    assert [last_sunday_of_march(y) for y in (2026, 2027, 2028, 2030)] == [29, 28, 26, 31]


def test_dst_jump_is_on_march_29(months):
    assert dst_jump_day(months) == 29


def test_table_year_is_current_year(months):
    assert detect_year(months, date(2026, 11, 19)) == 2026


def test_table_published_early_for_next_year(months):
    assert detect_year(months, date(2025, 12, 20)) == 2026


def test_unknown_year_falls_back_to_current_with_warning(months, caplog):
    assert detect_year(months, date(2027, 1, 10)) == 2027
    assert "introuvable" in caplog.text
