"""Calendar-month interval union. Imprecise year dates yield honest bounds."""

import re
from datetime import date

from clearcv.schemas import Employment, ExperienceEstimate

MONTHS = {
    name.lower(): i + 1
    for i, name in enumerate(
        [
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ]
    )
}
MONTHS.update({key[:3]: value for key, value in list(MONTHS.items())})\nMONTHS["sept"] = 9
MONTH_PATTERN = "(?:" + "|".join(sorted(MONTHS, key=len, reverse=True)) + ")"
DATE_TOKEN = rf"(?:\d{{4}}[-/]\d{{1,2}}[-/]\d{{1,2}}|(?:\d{{1,2}}\s+)?{MONTH_PATTERN}\.?\s+(?:\d{{1,2}},?\s+)?\d{{4}}|\d{{4}}[-/]\d{{1,2}}|\d{{1,2}}/\d{{4}}|\d{{4}}|Present|Current|Now|Ongoing|Today|Till\\s+Date|To\\s+Date)"
DATE_RANGE = re.compile(
    rf"(?<!\w)(?P<start>{DATE_TOKEN})\s*(?:[-–—]|\bto\b)\s*(?P<end>{DATE_TOKEN})(?!\d)", re.I
)


def month_index(year: int, month: int) -> int:
    return year * 12 + month - 1


def parse_date(value: str, today: date) -> tuple[int, int] | None:
    """Return earliest/latest month; no day-level precision is claimed."""
    value = value.strip().lower().replace(".", "")
    if re.fullmatch(r"(?:present|current|now|ongoing|today|till\\s+date|to\\s+date)", value):
        point = month_index(today.year, today.month)
        return point, point
    full = re.fullmatch(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", value)
    if full:
        try:
            parsed = date(int(full[1]), int(full[2]), int(full[3]))
        except ValueError:
            return None
        return parse_date(f"{parsed.year}-{parsed.month}", today)
    full = re.fullmatch(
        rf"(?:(\d{{1,2}})\s+)?({MONTH_PATTERN})\s+(?:(\d{{1,2}}),?\s+)?(\d{{4}})", value
    )
    if full and (full[1] or full[3]):
        if full[1] and full[3]:
            return None
        try:
            parsed = date(int(full[4]), MONTHS[full[2]], int(full[1] or full[3]))
        except ValueError:
            return None
        return parse_date(f"{parsed.year}-{parsed.month}", today)
    if re.fullmatch(r"\d{4}", value):
        year = int(value)
        if 1900 <= year <= 2100:
            return month_index(year, 1), month_index(year, 12)
        return None
    match = re.fullmatch(r"([a-z]+)\s+(\d{4})", value)
    if match and match[1] in MONTHS:
        year, month = int(match[2]), MONTHS[match[1]]
    else:
        match = re.fullmatch(r"(\d{4})[-/](\d{1,2})", value)
        if match:
            year, month = int(match[1]), int(match[2])
        else:
            match = re.fullmatch(r"(\d{1,2})/(\d{4})", value)
            if not match:
                return None
            year, month = int(match[2]), int(match[1])
    if not 1900 <= year <= 2100 or not 1 <= month <= 12:
        return None
    point = month_index(year, month)
    return point, point


def union_months(intervals: list[tuple[int, int]]) -> int:
    """Half-open intervals; adjacency merges; ordering is irrelevant."""
    total = 0
    right = None
    for start, end in sorted(intervals):
        if end <= start:
            continue
        if right is None or start > right:
            total += end - start
        elif end > right:
            total += end - right
        right = max(end, right) if right is not None else end
    return total


def estimate(jobs: list[Employment], today: date) -> tuple[ExperienceEstimate, list[str]]:
    lower, upper, warnings = [], [], []
    valid = 0
    current = month_index(today.year, today.month)
    for i, job in enumerate(jobs):
        start = parse_date(job.start.value, today) if job.start else None
        end = parse_date(job.end.value, today) if job.end else None
        if not start or not end:
            warnings.append(
                f"employment[{i}]: missing or unsupported date; excluded from experience."
            )
            continue
        if start[0] > current or end[0] > current or start[0] > end[1]:
            warnings.append(f"employment[{i}]: future or reversed date; excluded from experience.")
            continue
        start_max, end_max = min(start[1], current), min(end[1], current)
        # Completed end month is included; the current partial month is excluded.
        end_min_exclusive = end[0] + (end[0] < current)
        end_max_exclusive = end_max + (end_max < current)
        lower.append((start_max, end_min_exclusive))
        upper.append((start[0], end_max_exclusive))
        valid += 1
        if start[0] != start[1] or end[0] != end[1]:
            warnings.append(f"employment[{i}]: year-only date; experience shown as a range.")
    low, high = union_months(lower), union_months(upper)
    return ExperienceEstimate(
        lower_months=low,
        upper_months=high,
        lower_years=round(low / 12, 2),
        upper_years=round(high / 12, 2),
        dated_roles=valid,
        excluded_roles=len(jobs) - valid,
        as_of=today.isoformat(),
        policy="Union of calendar months; completed end month included, current partial month excluded; year-only dates yield bounds. This measures dated roles, not verified professional tenure.",
    ), warnings
