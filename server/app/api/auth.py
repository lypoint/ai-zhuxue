"""认证：监护人手机号+短信码（dev 固定码）+三要素核验注册；学生端凭绑定码+设备号登录。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import BindCode, Family, FamilySettings, Guardian, Student, StudentDevice
from ..schemas import GuardianRegisterIn, StudentLoginIn, TokenOut
from ..security import make_token
from ..services import guardian_verify
from ..services.guardian_verify import verify as verify_guardian

router = APIRouter(prefix="/auth", tags=["auth"])

# dev 模式固定短信码；生产接短信服务商并加频控
DEV_SMS_CODE = "123456"


@router.post("/guardian/register", response_model=TokenOut)
async def guardian_register(body: GuardianRegisterIn, db: Session = Depends(get_db)):
    if settings.env == "dev" and body.sms_code != DEV_SMS_CODE and body.sms_code != "":
        raise HTTPException(400, "invalid sms code")

    result = await verify_guardian(body.real_name, body.id_number, body.phone)
    if not result.passed:
        raise HTTPException(400, f"guardian verify failed: {result.detail}")

    guardian = db.query(Guardian).filter_by(phone=body.phone).first()
    if not guardian:
        # Initialize pricing before opening the family transaction.  If two
        # first registrations race, a config-row conflict cannot roll back a
        # partially created family.
        from ..services import subscription
        subscription.get_pricing_config(db)
        family = Family()
        db.add(family)
        db.flush()
        guardian = Guardian(family_id=family.id, phone=body.phone, nickname=body.nickname,
                            verified_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc))
        # 家庭设置从全局策略继承，家长后续仍可在端内覆盖。
        db.add(FamilySettings(
            family_id=family.id,
            daily_message_cap=settings.fence_daily_message_cap,
            quiet_enabled=settings.fence_quiet_enabled,
            quiet_start=settings.fence_quiet_start,
            quiet_end=settings.fence_quiet_end,
        ))
        db.add(guardian)
        db.flush()
        # P0 商业闭环：注册即开 30 天免费试用
        subscription.ensure_subscription(family.id, db)
        # 欢迎通知
        from ..models import Notification
        db.add(Notification(family_id=family.id, type="system",
                            title="欢迎使用 AI 助学",
                            body="已为您开启 30 天免费试用。请生成绑定码激活孩子端，开启受保护的学习之旅。"))
        db.commit()
    return TokenOut(token=make_token("guardian", guardian.id, guardian.family_id,
                                     guardian.token_version), role="guardian")


@router.post("/logout")
def logout(token: str = __import__("fastapi").Header(default="", alias="Authorization"),
           db: Session = Depends(get_db)):
    """登出：当前 token 版本 +1，该主体所有旧 token 立即失效。"""
    from fastapi import HTTPException as _HTTPException
    from ..security import parse_token
    try:
        payload = parse_token(token.removeprefix("Bearer "))
    except Exception:
        raise _HTTPException(401, "invalid token")
    role, sub = payload.get("role"), int(payload.get("sub", 0))
    model = Guardian if role == "guardian" else Student
    obj = db.get(model, sub)
    if not obj:
        raise _HTTPException(401, "not found")
    obj.token_version = (obj.token_version or 1) + 1
    db.commit()
    return {"ok": True}


@router.post("/student/login", response_model=TokenOut)
def student_login(body: StudentLoginIn, db: Session = Depends(get_db)):
    from datetime import datetime, timezone
    from ..services import subscription

    # Lock the family before the code and student rows.  PostgreSQL serializes
    # seat/device changes; SQLite's write transaction still gives the same
    # all-or-nothing result, while the conditional code update below protects
    # consume-once semantics on weaker row-locking backends.
    candidate = db.query(BindCode).filter_by(code=body.bind_code).first()
    family = (db.query(Family).filter_by(id=candidate.family_id).with_for_update().first()
              if candidate else None)
    bind = (db.query(BindCode).filter_by(code=body.bind_code,
                                         used_by_student_id=None,
                                         revoked_at=None)
            .with_for_update().first())
    now = datetime.now(timezone.utc)
    expires = bind.expires_at if bind and bind.expires_at.tzinfo else (bind.expires_at.replace(tzinfo=timezone.utc) if bind else now)
    if not bind or expires < now:
        raise HTTPException(400, "bind code invalid or expired")
    if bind.purpose not in ("new_student", "rebind"):
        raise HTTPException(400, "bind code purpose invalid")

    installation_id = body.installation_id or body.device_id
    legacy_device_login = body.installation_id is None and body.device_id is not None
    if not installation_id:
        raise HTTPException(422, "installation_id required")
    target = (db.query(Student).filter_by(id=bind.target_student_id,
                                          family_id=bind.family_id)
              .with_for_update().first() if bind.target_student_id else None)
    if bind.purpose == "rebind" and (not target or target.family_id != bind.family_id):
        raise HTTPException(400, "bind code target invalid")
    if target and target.family_id != bind.family_id:
        raise HTTPException(400, "bind code target invalid")
    student = target or (db.query(Student).filter_by(installation_id=installation_id)
                         .with_for_update().first())
    if student and student.family_id != bind.family_id:
        raise HTTPException(409, "installation already belongs to another family")
    if not student:
        # Current clients use installation_id and always obey the seat limit;
        # device_id-only callers remain temporarily compatible during rollout.
        if not subscription.can_add_student(bind.family_id, db) and not legacy_device_login:
            raise HTTPException(409, "no student seat available")
        student = Student(family_id=bind.family_id, device_id=installation_id,
                          installation_id=installation_id,
                          nickname=body.nickname or "我的孩子", grade_band="8-12")
        db.add(student)
        db.flush()
    elif not student.active:
        raise HTTPException(401, "student inactive")
    # 新设备绑定同一孩子时，吊销旧设备和旧 token；同一 installation 复用当前设备。
    device = db.query(StudentDevice).filter_by(installation_id=installation_id).first()
    switched = not device or device.student_id != student.id or not device.is_current
    if device and device.student_id != student.id:
        raise HTTPException(409, "installation already belongs to another student")
    if switched:
        replaced_count = db.query(StudentDevice).filter_by(
            student_id=student.id, is_current=True).count()
        db.query(StudentDevice).filter_by(student_id=student.id, is_current=True).update({
            StudentDevice.is_current: False,
            StudentDevice.revoked_at: datetime.now(timezone.utc),
        })
        if device:
            device.is_current = True
            device.revoked_at = None
            device.device_name = body.device_name or device.device_name
        else:
            device = StudentDevice(student_id=student.id, installation_id=installation_id,
                                   device_name=body.device_name or "学生设备")
            db.add(device)
        student.token_version = (student.token_version or 1) + 1
        student.installation_id = installation_id
        student.device_id = installation_id
    else:
        replaced_count = 0
        device.device_name = body.device_name or device.device_name
    try:
        db.flush()
        student.family_id = bind.family_id
        consumed_at = datetime.now(timezone.utc)
        consumed = (db.query(BindCode)
                    .filter(BindCode.id == bind.id,
                            BindCode.used_by_student_id.is_(None),
                            BindCode.revoked_at.is_(None))
                    .update({BindCode.used_by_student_id: student.id,
                             BindCode.used_at: consumed_at}, synchronize_session=False))
        if consumed != 1:
            db.rollback()
            raise HTTPException(409, "bind code already used")
        db.commit()
    except IntegrityError:
        db.rollback()
        # A concurrent login can win the installation_id/device unique key;
        # the caller must retry with the still-valid one-time code.
        raise HTTPException(409, "设备绑定冲突，请重新绑定后重试")
    return {
        "token": make_token("student", student.id, student.family_id,
                             student.token_version, device.id),
        "role": "student", "student_id": student.id,
        "student_device_id": device.id, "replaced_device_count": replaced_count,
    }
