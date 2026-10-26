"""Child overrides; legacy family settings supply defaults until a child is configured."""
from types import SimpleNamespace

from ..config import settings
from ..models import FamilySettings

FIELDS = ("daily_message_cap", "daily_minutes_cap", "quiet_enabled", "quiet_start", "quiet_end", "notify_fence")


def effective(student, db, family_settings=None):
    fs = family_settings or db.query(FamilySettings).filter_by(family_id=student.family_id).first()
    defaults = dict(daily_message_cap=settings.fence_daily_message_cap, daily_minutes_cap=60,
                    quiet_enabled=settings.fence_quiet_enabled, quiet_start=settings.fence_quiet_start,
                    quiet_end=settings.fence_quiet_end, notify_fence=True)
    return SimpleNamespace(**{name: getattr(student, name) if getattr(student, name) is not None
                              else getattr(fs, name) if fs else defaults[name] for name in FIELDS})
