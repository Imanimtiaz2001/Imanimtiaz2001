from datetime import date

import pytest
from hypothesis import given
from hypothesis import strategies as st

from clearcv.dates import estimate, parse_date, union_months
from clearcv.schemas import Employment, Fact


def job(start, end):
    def fact(value):
        return Fact(value=value, quote=value, line_ids=["p1-l1"]) if value else None

    return Employment(employer=None, role=None, start=fact(start), end=fact(end))


@pytest.mark.parametrize(
    "token", ["Jan 2024", "January 2024", "Jan. 2024", "2024-01", "01/2024", "2024/1"]
)
def test_month_formats(token):
    assert parse_date(token, date(2026, 10, 2)) == (2024 * 12, 2024 * 12)


@pytest.mark.parametrize(
    "token", ["Feb 1800", "2024-13", "00/2024", "Spring 2024", "unknown", "2024-01-50"]
)
def test_invalid_dates(token):
    assert parse_date(token, date(2026, 10, 2)) is None


def test_overlapping_employment():
    result, warnings = estimate(
        [job("Jan 2021", "Dec 2023"), job("Jan 2023", "Present")], date(2026, 10, 2)
    )
    assert result.lower_months == result.upper_months == 69
    assert result.lower_years == 5.75 and warnings == []


def test_year_precision():
    result, warnings = estimate([job("2021", "2023")], date(2026, 10, 2))
    assert (result.lower_months, result.upper_months) == (14, 36) and len(warnings) == 1


def test_future_reversed_missing_dates():
    result, warnings = estimate(
        [job("2030", "Present"), job("Jan 2025", "Dec 2024"), job(None, "Present")],
        date(2026, 10, 2),
    )
    assert result.dated_roles == 0 and result.excluded_roles == 3 and len(warnings) == 3


def test_current_month_is_not_complete():
    result, _ = estimate([job("Oct 2026", "Present")], date(2026, 10, 2))
    assert result.upper_months == 0
    result, _ = estimate([job("Jan 2026", "Present")], date(2026, 10, 2))
    assert result.upper_months == 9


@given(st.lists(st.tuples(st.integers(0, 80), st.integers(0, 80)), max_size=30))
def test_interval_union_matches_set(intervals):
    expected = len({month for start, end in intervals for month in range(start, end)})
    assert union_months(intervals) == expected
    assert union_months(intervals * 2) == expected
    assert union_months(list(reversed(intervals))) == expected


@pytest.mark.parametrize("token", ["17 Jan 2024", "January 17, 2024", "2024-01-17"])
def test_full_dates_reduce_to_calendar_month(token):
    assert parse_date(token, date(2026, 10, 2)) == (2024 * 12, 2024 * 12)
