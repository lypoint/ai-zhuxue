"""绑定码：家长端生成（二维码内容），学生端输入/扫码后绑定。"""
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import BindCode, Family, Student
from ..api.deps import current_guardian
from ..models import Guardian
from ..schemas import BindCodeOut

router = APIRouter(prefix="/bind", tags=["bind"])


def _new_code(db: Session, family_id: int, purpose: str = "new_student",
              target_student_id: int | None = None) -> BindCode:
    code = secrets.token_hex(4).upper()
    bind = BindCode(family_id=family_id, code=code, purpose=purpose,
                    target_student_id=target_student_id,
                    expires_at=datetime.now(timezone.utc) + timedelta(minutes=10))
    db.add(bind)
    db.flush()
    return bind


@router.post("/code", response_model=BindCodeOut)
def create_bind_code(body: dict | None = None, guardian: Guardian = Depends(current_guardian), db: Session = Depends(get_db)):
    body = body or {}
    db.query(Family).filter_by(id=guardian.family_id).with_for_update().first()
    purpose = body.get("purpose", "new_student")
    if purpose not in ("new_student", "rebind"):
        raise HTTPException(422, "purpose 须为 new_student 或 rebind")
    target_id = body.get("target_student_id")
    if purpose == "rebind":
        try:
            target_id = int(target_id)
        except (TypeError, ValueError):
            raise HTTPException(422, "rebind 必须指定 target_student_id")
        target = (db.query(Student).filter_by(id=target_id, family_id=guardian.family_id)
                  .with_for_update().first())
        if not target or target.family_id != guardian.family_id or not target.active:
            raise HTTPException(404, "student not found")
        db.query(BindCode).filter_by(family_id=guardian.family_id,
                                     target_student_id=target_id,
                                     used_by_student_id=None,
                                     revoked_at=None).update({BindCode.revoked_at: datetime.now(timezone.utc)})
    elif target_id is not None:
        raise HTTPException(422, "new_student 不应指定 target_student_id")
    bind = _new_code(db, guardian.family_id, purpose=purpose, target_student_id=target_id)
    db.commit()
    return BindCodeOut(code=bind.code, expires_at=bind.expires_at,
                       purpose=purpose, target_student_id=target_id)


@router.get("/codes", response_model=list[BindCodeOut])
def list_active_codes(guardian: Guardian = Depends(current_guardian), db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    codes = (db.query(BindCode)
             .filter(BindCode.family_id == guardian.family_id,
                     BindCode.expires_at > now, BindCode.used_by_student_id.is_(None),
                     BindCode.revoked_at.is_(None))
             .all())
    return codes


@router.delete("/codes/{code}")
def revoke_bind_code(code: str, guardian: Guardian = Depends(current_guardian),
                    db: Session = Depends(get_db)):
    """家长主动作废尚未使用的绑定码。"""
    db.query(Family).filter_by(id=guardian.family_id).with_for_update().first()
    bind = (db.query(BindCode)
            .filter_by(code=code.strip().upper(), family_id=guardian.family_id,
                       used_by_student_id=None, revoked_at=None).first())
    if not bind:
        raise HTTPException(404, "bind code not found")
    bind.revoked_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True, "revoked": True, "code": bind.code}
