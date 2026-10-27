"""First-party facts committed with business data; no outbound Analytics requests."""
import json
from datetime import datetime, timezone

from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..models import AnalyticsEvent, Family

FACTS = {"family_registered", "trial_started", "child_created", "device_connected",
         "question_accepted", "learning_completed", "payment_confirmed", "subscription_activated", "entitlement_revoked"}
STUDENT_EVENTS = {"student_page_view", "guide_completed", "teacher_selected", "question_submitted",
                  "answer_received", "answer_failed", "answer_cancelled"}
PARENT_EVENTS = {"page_view", "view_subscription", "begin_checkout", "checkout_open", "checkout_closed",
                 "checkout_error", "subscription_verify", "subscription_manage"}
PAGES = {"home", "children", "activity", "schedule", "favorites", "learning", "grades", "assessments",
         "notifications", "subscription", "settings", "chat", "stats", "history", "other"}


def safe_properties(values):
    safe = {}
    enums = {"page": PAGES, "result": {"success", "failure"},
             "provider": {"google", "waffo", "appstore", "googleplay", "wechat", "demo"},
             "environment": {"test", "production"}, "mode": {"stream", "single"},
             "input": {"text", "image"}, "action": {"allow", "rewrite"}}
    for name, allowed in enums.items():
        if isinstance(values.get(name), str) and values[name] in allowed:
            safe[name] = values[name]
    if type(values.get("seat_count")) is int and 1 <= values["seat_count"] <= 1000:
        safe["seat_count"] = values["seat_count"]
    return safe


def record(db, name, family_id, key, *, student_id=None, source="server", at=None, **properties):
    if name not in FACTS | STUDENT_EVENTS | PARENT_EVENTS:
        raise ValueError("Unknown operations event")
    if source not in {"server", "parent_web", "student_web"}:
        raise ValueError("Unknown operations source")
    if db.get(Family, family_id).access_disabled:
        return
    # Callers use internal row IDs/UUIDs; never an email, device ID, purchase token or content.
    key = f"{family_id}:{key}"
    if len(key) > 100:
        raise ValueError("Event key too long")
    insert = pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
    db.execute(insert(AnalyticsEvent).values(key=key, name=name, family_id=family_id,
        student_id=student_id, source=source, occurred_at=at or datetime.now(timezone.utc),
        properties=json.dumps(safe_properties(properties))).on_conflict_do_nothing(index_elements=["key"]))
