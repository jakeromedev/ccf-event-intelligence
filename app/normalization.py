"""Authoritative normalization rules for event dashboard metrics.

The import layer preserves source values.  This module turns those values into
the small, auditable category sets used by Phase 1 analytics.
"""

import calendar
import re
from datetime import date, datetime


GENDER_CATEGORIES = (
    ("male", "Male"),
    ("female", "Female"),
    ("unknown", "Unknown"),
)

LIFE_STAGE_CATEGORIES = (
    ("single", "Single"),
    ("single-parent", "Single Parent"),
    ("married", "Married"),
    ("unknown", "Unknown"),
)

AGE_BUCKETS = (
    "Below 20",
    "20–25",
    "26–30",
    "31–35",
    "36–40",
    "41+",
    "Unknown",
)


def _clean(value):
    return " ".join(str(value or "").strip().split())


def normalize_registration_type(ticket_name=None, event_name=None):
    """Classify a ticket-linked registration without using contact fields.

    Current CCF exports identify volunteer populations through the ticket or
    export event label. All other registrant rows are participants. Matching is
    deliberately limited to the complete word ``volunteer(s)`` so unrelated
    ticket labels are not accidentally reclassified.
    """
    source = " ".join(value for value in (_clean(ticket_name), _clean(event_name)) if value)
    return "volunteer" if re.search(r"\bvolunteers?\b", source, re.IGNORECASE) else "participant"


def normalize_gender(value):
    normalized = _clean(value).casefold()
    if normalized in ("male", "m"):
        return "male"
    if normalized in ("female", "f"):
        return "female"
    return "unknown"


def normalize_life_stage(value):
    normalized = re.sub(r"[\s_-]+", " ", _clean(value).casefold()).strip()
    if normalized == "single":
        return "single"
    if normalized in ("single parent", "solo parent"):
        return "single-parent"
    if normalized == "married":
        return "married"
    return "unknown"


def parse_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    cleaned = _clean(value)
    if not cleaned:
        return None
    # ISO is the normalized database/input format. The additional formats make
    # optional full-DOB source fields tolerant of common CSV export variants.
    for parser in (
        lambda raw: date.fromisoformat(raw),
        lambda raw: datetime.strptime(raw, "%m/%d/%Y").date(),
        lambda raw: datetime.strptime(raw, "%B %d, %Y").date(),
        lambda raw: datetime.strptime(raw, "%b %d, %Y").date(),
    ):
        try:
            return parser(cleaned)
        except ValueError:
            continue
    return None


def calculate_age_at_event(
    birth_date,
    event_date,
    birth_month=None,
    birth_year=None,
):
    """Return age at the event, or ``None`` for missing/invalid input.

    A full birth date receives birthday-day precision. Existing exports only
    contain birth month/year; for those rows the birthday is treated as the
    first day of the supplied month, which is the narrowest reproducible rule
    possible without inventing a day.
    """
    event = parse_date(event_date)
    if event is None:
        return None

    birth = parse_date(birth_date)
    if birth is not None:
        age = event.year - birth.year - ((event.month, event.day) < (birth.month, birth.day))
    else:
        month_value = _clean(birth_month)
        year_value = _clean(birth_year)
        if not month_value or not year_value:
            return None
        month_lookup = {
            name.casefold(): number
            for number, name in enumerate(calendar.month_name)
            if name
        }
        month_lookup.update(
            {
                name.casefold(): number
                for number, name in enumerate(calendar.month_abbr)
                if name
            }
        )
        try:
            month = int(month_value) if month_value.isdigit() else month_lookup[month_value.casefold()]
            year = int(year_value)
            if month < 1 or month > 12:
                return None
        except (KeyError, TypeError, ValueError):
            return None
        age = event.year - year - int(event.month < month)

    return age if 0 <= age <= 120 else None


def get_age_bucket(age):
    if age is None or isinstance(age, bool):
        return "Unknown"
    try:
        age = int(age)
    except (TypeError, ValueError):
        return "Unknown"
    if age < 0 or age > 120:
        return "Unknown"
    if age < 20:
        return "Below 20"
    if age <= 25:
        return "20–25"
    if age <= 30:
        return "26–30"
    if age <= 35:
        return "31–35"
    if age <= 40:
        return "36–40"
    return "41+"
