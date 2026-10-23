"""Authenticated deletion requests and operator-only personal-data erasure."""
from datetime import datetime, timedelta, timezone
import uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .. import models as m
from ..api.deps import require_family_access


def deactivate_student(db: Session, student: m.Student) -> None:
    """Caller holds the family lock; keep learning records available to guardians."""
    now = datetime.now(timezone.utc)
    student.active = False
    student.nickname = "已注销"
    student.device_id = f"deleted-{uuid.uuid4().hex}"
    student.installation_id = None
    student.forbidden_words_json = "[]"
    student.fence_level = "strict"
    student.token_version = (student.token_version or 1) + 1
    for device in db.query(m.StudentDevice).filter_by(student_id=student.id).all():
        device.is_current = False
        device.revoked_at = device.revoked_at or now
        device.installation_id = f"deleted-{uuid.uuid4().hex}"
    db.query(m.BindCode).filter_by(target_student_id=student.id, revoked_at=None).update(
        {m.BindCode.revoked_at: now}, synchronize_session=False)


def request_deletion(db: Session, guardian: m.Guardian) -> m.AccountDeletionRequest:
    family = db.query(m.Family).filter_by(id=guardian.family_id).populate_existing().with_for_update().one()
    existing = db.get(m.AccountDeletionRequest, family.id)
    if existing:
        if existing.guardian_id != guardian.id:
            raise HTTPException(403, "请联系 support@gker.net 处理共同家庭的删除申请")
        return existing
    require_family_access(family.id, db)
    # A guardian must never silently delete another adult's shared data.
    if db.query(m.Guardian).filter_by(family_id=family.id).count() != 1:
        raise HTTPException(409, "请联系 support@gker.net 处理共同家庭的删除申请")
    row = m.AccountDeletionRequest(family_id=family.id, guardian_id=guardian.id)
    db.add(row)
    family.access_disabled = True
    # Release unique identities immediately; a new registration gets a separate family.
    guardian.phone = guardian.google_sub = guardian.username = guardian.password_hash = None
    now = datetime.now(timezone.utc)
    for student in db.query(m.Student).filter_by(family_id=family.id).all():
        deactivate_student(db, student)
    db.query(m.BindCode).filter_by(family_id=family.id, revoked_at=None).update(
        {m.BindCode.revoked_at: now}, synchronize_session=False)
    # Family access blocks all normal sessions; retain the token version only
    # so a lost HTTP response can safely retry this one idempotent operation.
    db.add(m.AdminLog(admin=f"guardian:{guardian.id}", action="account.deletion_requested",
                      detail=f"family_id={family.id}"))
    db.flush()
    return row


def complete_deletion(db: Session, family_id: int) -> m.AccountDeletionRequest:
    family = db.query(m.Family).filter_by(id=family_id).populate_existing().with_for_update().one_or_none()
    row = db.get(m.AccountDeletionRequest, family_id)
    if not family or not row:
        raise ValueError("No deletion request for this family")
    if row.completed_at:
        return row
    if not family.access_disabled:
        raise ValueError("Family must remain disabled before erasure")
    now = datetime.now(timezone.utc)
    requested = row.created_at.replace(tzinfo=timezone.utc) if row.created_at.tzinfo is None else row.created_at
    # Allow pre-existing chat/assessment requests to finish before the final purge.
    if now - requested < timedelta(days=1):
        raise ValueError("Wait at least 24 hours after the request before erasure")
    students = db.query(m.Student).filter_by(family_id=family_id).all()
    ids = [s.id for s in students]
    convs = db.query(m.Conversation.id).filter(m.Conversation.student_id.in_(ids))
    grades = db.query(m.StudentGrade.id).filter(m.StudentGrade.student_id.in_(ids))
    academics = db.query(m.AcademicAssessment.id).filter(m.AcademicAssessment.student_id.in_(ids))
    wellbeing = db.query(m.WellbeingAssessment.id).filter(m.WellbeingAssessment.student_id.in_(ids))
    db.query(m.AssessmentAudit).filter(
        ((m.AssessmentAudit.assessment_type == "academic") & m.AssessmentAudit.assessment_id.in_(academics)) |
        ((m.AssessmentAudit.assessment_type == "wellbeing") & m.AssessmentAudit.assessment_id.in_(wellbeing))
    ).delete(synchronize_session=False)
    db.query(m.StudentGradeVersion).filter(m.StudentGradeVersion.grade_id.in_(grades)).delete(synchronize_session=False)
    db.query(m.Notification).filter_by(family_id=family_id).delete(synchronize_session=False)
    for model in (m.Favorite, m.LearningFeedback, m.LearningFeedbackEvent, m.RewardRedemption,
                  m.RewardAgreement, m.LearningDayReward, m.FenceFeedback, m.FenceEvent):
        db.query(model).filter(model.student_id.in_(ids)).delete(synchronize_session=False)
    from .media import detach_student
    for student_id in ids:
        detach_student(db, student_id)
    db.query(m.Message).filter(m.Message.conversation_id.in_(convs)).delete(synchronize_session=False)
    db.query(m.Conversation).filter(m.Conversation.student_id.in_(ids)).delete(synchronize_session=False)
    for model in (m.StudentGrade, m.AcademicAssessment, m.WellbeingAssessment,
                  m.StudentDevice, m.ActiveTime, m.UsageLog):
        db.query(model).filter(model.student_id.in_(ids)).delete(synchronize_session=False)
    for model in (m.BindCode, m.FamilySettings, m.Subscription):
        db.query(model).filter_by(family_id=family_id).delete(synchronize_session=False)
    for guardian in db.query(m.Guardian).filter_by(family_id=family_id):
        guardian.phone = guardian.google_sub = guardian.username = guardian.password_hash = None
        guardian.nickname = ""
        guardian.is_review = False
        guardian.token_version += 1
    for student in students:
        student.nickname = ""
        student.installation_id = None
        student.device_id = f"deleted-{uuid.uuid4().hex}"
        student.grade_band = "8-12"
        student.last_teacher_group_id = None
        student.forbidden_words_json = "[]"
        student.fence_level = "strict"
        student.active = False
        student.token_version += 1
    family.tag = None
    # Keep non-identifying ID tombstones to prevent old JWT subjects being
    # reassigned. Payment records remain isolated for settlement/refund/security.
    row.completed_at = now
    db.add(m.AdminLog(admin="local-cli", action="account.deletion_completed", detail=f"family_id={family_id}"))
    db.flush()
    return row
