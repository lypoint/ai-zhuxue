"""Business dates use TZ_OFFSET_HOURS; database timestamps remain UTC."""
from datetime import datetime, timedelta, timezone

from .config import settings


def local_now():
    return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=settings.tz_offset_hours)


def utc_bounds(start: str, end: str | None = None):
    offset = timedelta(hours=settings.tz_offset_hours)
    return (datetime.fromisoformat(start) - offset,
            datetime.fromisoformat(end or start) + timedelta(days=1) - offset)
