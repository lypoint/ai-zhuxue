"""Family business dates; timestamps remain UTC and legacy families keep their offset."""
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .config import settings


family_timezone = ContextVar("family_timezone", default=None)
timezone_transition = ContextVar("timezone_transition", default=None)


def business_zone():
    name = family_timezone.get()
    return ZoneInfo(name) if name else timezone(timedelta(hours=settings.tz_offset_hours))


def as_utc(stamp):
    return stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp.astimezone(timezone.utc)


def local_datetime(stamp):
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(business_zone()).replace(tzinfo=None)


def local_now():
    return local_datetime(datetime.now(timezone.utc))


def utc_bounds(start: str, end: str | None = None):
    zone = business_zone()
    first = datetime.fromisoformat(start).replace(tzinfo=zone)
    last = (datetime.fromisoformat(end or start) + timedelta(days=1)).replace(tzinfo=zone)
    return (first.astimezone(timezone.utc).replace(tzinfo=None),
            last.astimezone(timezone.utc).replace(tzinfo=None))


def previous_business_day():
    transition = timezone_transition.get()
    if transition and transition[0] == local_now().date():
        return transition[1]
    return None


def quota_start(now=None):
    now = now or local_now()
    start = utc_bounds(now.date().isoformat())[0]
    transition = timezone_transition.get()
    if transition and transition[0] == now.date():
        start = min(start, transition[2])
    return start


class FamilyTimezoneMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        name, transition = None, None
        if scope["type"] == "http":
            from .db import SessionLocal
            from .models import Family
            from .security import parse_token
            headers = dict(scope.get("headers", []))
            try:
                payload = parse_token(headers.get(b"authorization", b"").decode().removeprefix("Bearer "))
                if payload.get("role") in ("guardian", "student"):
                    with SessionLocal() as db:
                        family = db.get(Family, int(payload["family_id"]))
                        name = family.timezone if family else None
                        if name and family.timezone_changed_at:
                            stamp = as_utc(family.timezone_changed_at)
                            zone = ZoneInfo(name)
                            old = (ZoneInfo(family.previous_timezone) if family.previous_timezone
                                   else timezone(timedelta(hours=settings.tz_offset_hours)))
                            old_day = stamp.astimezone(old).date()
                            floor = datetime.combine(old_day, datetime.min.time(), old).astimezone(timezone.utc).replace(tzinfo=None)
                            transition = (stamp.astimezone(zone).date(), old_day.isoformat(), floor)
            except (ValueError, KeyError, __import__("jwt").PyJWTError):
                pass
        marker = family_timezone.set(name)
        transition_marker = timezone_transition.set(transition)
        try:
            await self.app(scope, receive, send)
        finally:
            family_timezone.reset(marker)
            timezone_transition.reset(transition_marker)
