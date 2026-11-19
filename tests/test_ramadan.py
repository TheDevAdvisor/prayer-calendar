from datetime import date, timedelta

from prayer_calendar.ramadan import is_ramadan, normalize_overrides, ramadan_ranges


def _year(y):
    return [date(y, 1, 1) + timedelta(days=i) for i in range(366 if y % 4 == 0 else 365)]


def test_umm_al_qura_1448():
    # 1 Ramadan 1448 = 08/02/2027, 1 Chawwal = 09/03/2027
    assert not is_ramadan(date(2027, 2, 7))
    assert is_ramadan(date(2027, 2, 8))
    assert is_ramadan(date(2027, 3, 8))
    assert not is_ramadan(date(2027, 3, 9))


def test_ranges_2026():
    assert ramadan_ranges(_year(2026)) == [(date(2026, 2, 18), date(2026, 3, 19))]


def test_hijri_adjustment_shifts_the_month():
    assert ramadan_ranges(_year(2027), adjustment=-1) == [(date(2027, 2, 9), date(2027, 3, 9))]


def test_override_replaces_the_calculation():
    overrides = normalize_overrides({2027: {"start": date(2027, 2, 9), "end": date(2027, 3, 10)}})
    assert ramadan_ranges(_year(2027), overrides=overrides) == [(date(2027, 2, 9), date(2027, 3, 10))]
    # une autre année reste calculée
    assert ramadan_ranges(_year(2026), overrides=overrides) == [(date(2026, 2, 18), date(2026, 3, 19))]


def test_overrides_accept_strings():
    assert normalize_overrides({"2027": {"start": "2027-02-08", "end": "2027-03-08"}}) == {
        2027: {"start": date(2027, 2, 8), "end": date(2027, 3, 8)}
    }
