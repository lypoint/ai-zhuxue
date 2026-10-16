import jwt as pyjwt
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Family, Guardian, Student, StudentDevice
from ..security import parse_token


def require_family_access(family_id: int, db: Session):
    family = db.get(Family, family_id)
    if not family or family.access_disabled:
        raise HTTPException(401, "账号已停用，请联系支持")


def guardian_identity(token: str = Header(alias="Authorization"), db: Session = Depends(get_db)) -> Guardian:
    """Identity only, for deletion retries; normal routes use current_guardian."""
    try:
        payload = parse_token(token.removeprefix("Bearer "))
    except pyjwt.PyJWTError:
        raise HTTPException(401, "invalid token")
    if payload.get("role") != "guardian":
        raise HTTPException(403, "guardian token required")
    guardian = db.get(Guardian, int(payload["sub"]))
    if not guardian:
        raise HTTPException(401, "guardian not found")
    if guardian.token_version != payload.get("ver"):
        raise HTTPException(401, "登录已失效，请重新登录")
    return guardian


def current_guardian(guardian: Guardian = Depends(guardian_identity), db: Session = Depends(get_db)) -> Guardian:
    require_family_access(guardian.family_id, db)
    return guardian


def current_student(token: str = Header(alias="Authorization"), db: Session = Depends(get_db)) -> Student:
    try:
        payload = parse_token(token.removeprefix("Bearer "))
    except pyjwt.PyJWTError:
        raise HTTPException(401, "invalid token")
    if payload.get("role") != "student":
        raise HTTPException(403, "student token required")
    student = db.get(Student, int(payload["sub"]))
    if not student or not student.active:
        raise HTTPException(401, "student not found or inactive")
    require_family_access(student.family_id, db)
    if student.token_version != payload.get("ver"):
        raise HTTPException(401, "登录已失效，请重新绑定")
    device_id = payload.get("device_id")
    if device_id is None:
        raise HTTPException(401, "学生令牌缺少设备信息，请重新绑定")
    device = db.get(StudentDevice, int(device_id))
    if not device or device.student_id != student.id or not device.is_current or device.revoked_at:
        raise HTTPException(401, "此孩子已在其他设备重新绑定，请重新绑定")
    device.last_seen_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    db.commit()
    return student


def family_of_guardian(guardian: Guardian, db: Session) -> Family:
    return db.get(Family, guardian.family_id)
