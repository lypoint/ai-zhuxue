"""认证：监护人手机号+短信码（dev 固定码）+三要素核验注册；学生端凭绑定码+设备号登录。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import Family, FamilySettings, Guardian, Student
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
        from ..services import subscription
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
    from ..models import BindCode
    from datetime import datetime, timezone

    bind = db.query(BindCode).filter_by(code=body.bind_code, used_by_student_id=None).first()
    now = datetime.now(timezone.utc).replace(tzinfo=None)  # sqlite 落库为 naive
    if not bind or bind.expires_at < now:
        raise HTTPException(400, "bind code invalid or expired")

    student = db.query(Student).filter_by(device_id=body.device_id).first()
    if not student:
        student = Student(family_id=bind.family_id, device_id=body.device_id,
                          nickname=body.nickname or "我的孩子", grade_band="8-12")
        db.add(student)
        db.flush()  # 先取 id 再标记绑定码已用，否则 used 标记落库为 NULL（码可被重放）
    student.family_id = bind.family_id
    bind.used_by_student_id = student.id
    db.commit()
    return TokenOut(token=make_token("student", student.id, student.family_id,
                                     student.token_version), role="student")
