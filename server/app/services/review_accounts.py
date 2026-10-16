"""Local operator lifecycle for isolated store-review families."""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..config import settings
from ..models import AdminLog, BindCode, Family, FamilySettings, Guardian, Student, StudentDevice, Subscription
from ..security import hash_password


def create_review_account(db: Session, username: str, password: str) -> Guardian:
    if db.query(Guardian).filter_by(username=username).first():
        raise ValueError("Account already exists; creation never re-enables an account")
    family = Family()
    db.add(family)
    db.flush()
    guardian = Guardian(family_id=family.id, username=username, password_hash=hash_password(password),
                        is_review=True, nickname="应用审核")
    db.add_all([guardian, FamilySettings(family_id=family.id,
                daily_message_cap=settings.fence_daily_message_cap,
                quiet_enabled=settings.fence_quiet_enabled,
                quiet_start=settings.fence_quiet_start, quiet_end=settings.fence_quiet_end),
                Subscription(family_id=family.id, plan="permanent", seat_count=100,
                             provider="review", expires_at=datetime(9999, 12, 31, tzinfo=timezone.utc))])
    db.flush()
    db.add(AdminLog(admin="local-cli", action="review_account_created", detail=f"family_id={family.id}"))
    return guardian


def disable_review_account(db: Session, username: str) -> dict:
    guardian = db.query(Guardian).filter_by(username=username, is_review=True).one_or_none()
    if guardian is None:
        raise ValueError("Managed review account not found")
    family = db.query(Family).filter_by(id=guardian.family_id).with_for_update().one()
    family.access_disabled = True
    now = datetime.now(timezone.utc)
    for parent in db.query(Guardian).filter_by(family_id=family.id):
        parent.token_version += 1
    students = db.query(Student).filter_by(family_id=family.id).all()
    for student in students:
        student.active = False
        student.token_version += 1
    ids = [student.id for student in students]
    db.query(StudentDevice).filter(StudentDevice.student_id.in_(ids)).update(
        {StudentDevice.is_current: False, StudentDevice.revoked_at: now}, synchronize_session=False)
    db.query(BindCode).filter_by(family_id=family.id, revoked_at=None).update(
        {BindCode.revoked_at: now}, synchronize_session=False)
    db.add(AdminLog(admin="local-cli", action="review_account_disabled", detail=f"family_id={family.id}"))
    return {"family_id": family.id, "disabled": True, "students_disabled": len(students)}
