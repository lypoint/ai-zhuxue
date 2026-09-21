"""绑定码：家长端生成（二维码内容），学生端输入/扫码后绑定。"""
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import BindCode
from ..api.deps import current_guardian
from ..models import Guardian
from ..schemas import BindCodeOut

router = APIRouter(prefix="/bind", tags=["bind"])


@router.post("/code", response_model=BindCodeOut)
def create_bind_code(guardian: Guardian = Depends(current_guardian), db: Session = Depends(get_db)):
    code = secrets.token_hex(4).upper()  # 8位，如 A3F9C2B1
    bind = BindCode(family_id=guardian.family_id, code=code,
                    expires_at=datetime.now(timezone.utc) + timedelta(minutes=10))
    db.add(bind)
    db.commit()
    return BindCodeOut(code=code, expires_at=bind.expires_at)


@router.get("/codes", response_model=list[BindCodeOut])
def list_active_codes(guardian: Guardian = Depends(current_guardian), db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    codes = (db.query(BindCode)
             .filter(BindCode.family_id == guardian.family_id,
                     BindCode.expires_at > now, BindCode.used_by_student_id.is_(None))
             .all())
    return codes
