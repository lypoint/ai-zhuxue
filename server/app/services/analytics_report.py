"""Family-level UTC cohorts. Browser evidence and server facts stay distinct."""
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from ..local_time import as_utc
from ..config import settings
from ..models import AnalyticsEvent as E, Family, Guardian, StoreAccount


def report(db, start, end, *, include_test=False, now=None):
    now = as_utc(now or datetime.now(timezone.utc))
    begin = datetime.combine(start, datetime.min.time(), timezone.utc)
    finish = datetime.combine(end + timedelta(days=1), datetime.min.time(), timezone.utc)
    allowed = select(Family.id).where(Family.access_disabled.is_(False), ~select(Guardian.id).where(
        Guardian.family_id == Family.id, Guardian.is_review.is_(True)).exists())
    if not include_test:
        test_tokens = {token.strip().lower() for values in (settings.store_test_account_tokens,
            settings.creem_test_account_tokens, settings.paddle_sandbox_test_account_tokens)
            for token in values.split(",") if token.strip()}
        allowed = allowed.where(~Family.id.in_(select(StoreAccount.family_id).where(
            StoreAccount.account_token.in_(test_tokens))))
    registrations = db.query(E.family_id, func.min(E.occurred_at)).filter(
        E.name == "family_registered", E.source == "server", E.family_id.in_(allowed),
        E.occurred_at >= begin, E.occurred_at < finish, E.occurred_at <= now).group_by(E.family_id).all()
    cohort = {family: as_utc(at) for family, at in registrations}
    # shortcut: raw cohort scans; use daily aggregates when report volume outgrows the request budget.
    rows = db.query(E.family_id, E.name, E.occurred_at, E.properties, E.source).filter(
        E.family_id.in_(list(cohort)), E.occurred_at >= begin,
        E.occurred_at < finish + timedelta(days=61), E.occurred_at <= now).order_by(E.occurred_at).all()
    times = {}
    learning = {}
    for family, name, at, raw, source in rows:
        at = as_utc(at)
        if at < cohort[family]:
            continue
        props = json.loads(raw)
        if name in {"payment_confirmed", "subscription_activated"} and not include_test and props.get("environment") != "production":
            continue
        times.setdefault((family, name), []).append(at)
        if name == "learning_completed" and source == "server":
            learning.setdefault(family, set()).add(at.date())

    def funnel(names, days, anchors=None):
        anchors = cohort if anchors is None else anchors
        eligible = {family: at for family, at in anchors.items() if at + timedelta(days=days) <= now}
        counts = [len(eligible)] + [0] * (len(names) - 1)
        for family, registered in eligible.items():
            previous = registered
            for index, name in enumerate(names[1:], 1):
                match = next((at for at in times.get((family, name), [])
                              if previous <= at <= registered + timedelta(days=days)), None)
                if match is None:
                    break
                counts[index] += 1
                previous = match
        return {"window_days": days, "mature_families": len(eligible), "pending_families": len(anchors) - len(eligible),
                "steps": [{"event": name, "families": count,
                           "from_previous": count / counts[i - 1] if i and counts[i - 1] else None,
                           "from_start": count / counts[0] if counts[0] else None}
                          for i, (name, count) in enumerate(zip(names, counts))]}

    retention = []
    for day in (1, 7, 30):
        eligible = returned = 0
        for family, dates in learning.items():
            first = min(dates)
            if first > (cohort[family] + timedelta(days=30)).date():
                continue
            target = first + timedelta(days=day)
            # Only complete UTC days; today's activity must not depress retention.
            if target < now.date():
                eligible += 1
                returned += target in dates
        retention.append({"day": day, "eligible_families": eligible, "returned_families": returned,
                          "rate": returned / eligible if eligible else None})
    views = {family: min(at) for (family, name), at in times.items() if name == "view_subscription"}
    entries = {family: min(at) for (family, name), at in times.items() if name == "student_page_view"}
    return {"start": start.isoformat(), "end": end.isoformat(), "timezone": "UTC", "as_of": now.isoformat(),
            "include_test": include_test, "registered_families": len(cohort),
            "activation": funnel(["family_registered", "device_connected", "question_accepted", "learning_completed"], 7),
            "checkout": funnel(["view_subscription", "begin_checkout", "payment_confirmed"], 30, views),
            "student_experience": funnel(["student_page_view", "question_submitted", "answer_received"], 7, entries),
            "trial_to_paid": funnel(["family_registered", "payment_confirmed"], 30),
            "subscription_activation": funnel(["family_registered", "subscription_activated"], 30),
            "retention": retention,
            "coverage": {"parent_web": "consented authenticated samples", "student_web": "authenticated families, no consent gate", "payments": "positive-price verified transactions; Google price unavailable excluded",
                         "history": "new events only; no historical backfill; erasure removes families"}}
