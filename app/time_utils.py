"""Operational timestamp helpers.

Database timestamps are stored as naive UTC values.  Convert them only when
presenting them so existing and future records share one storage convention.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


DISPLAY_TIMEZONE_NAME = "Asia/Manila"
UTC = timezone.utc
# The Philippines has observed UTC+08:00 continuously since 1978. Application
# operational records are contemporary, so a fixed offset avoids depending on
# operating-system timezone data in minimal production containers.
MANILA_TIMEZONE = timezone(timedelta(hours=8), name="PHT")


def utc_now():
    """Return the current UTC time in the database's naive DATETIME shape."""
    return datetime.now(UTC).replace(tzinfo=None)


def as_manila_time(value):
    """Interpret naive operational timestamps as UTC and return Manila time."""
    if value in (None, ""):
        return None
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(MANILA_TIMEZONE)


def format_operational_datetime(value):
    """Format an operational timestamp for display in Asia/Manila."""
    if value in (None, ""):
        return "—"
    try:
        parsed = as_manila_time(value)
    except (TypeError, ValueError):
        return value
    date_part = parsed.strftime("%b %d, %Y").replace(" 0", " ")
    time_part = parsed.strftime("%I:%M %p").lstrip("0")
    return "{} · {} PHT".format(date_part, time_part)
