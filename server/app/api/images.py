"""Authenticated private media and student diagram requests."""
import asyncio
import time
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .deps import current_student, guardian_identity, require_family_access
from .chat import _check_policy, _student_conversation, _teacher
from ..config import settings
from ..db import get_db
from ..models import Conversation, ImageJob, MediaAsset, Message, Student
from ..ratelimit import _hit
from ..security import parse_token
from ..services import image_chat, image_jobs, media
from ..services.teacher_channels import current_channel

router = APIRouter(tags=["images"])


def _limited(db, key, count):
    allowed = _hit(db, key, count, int(time.time() // 60))
    db.commit()
    return allowed


class UploadIn(BaseModel):
    conversation_id: int | None = None
    teacher_id: int | None = None


@router.post("/media/uploads")
def upload(body: UploadIn, student: Student = Depends(current_student), db: Session = Depends(get_db),
           channel: str = Depends(current_channel)):
    if not settings.image_features_enabled:
        raise HTTPException(503, "图片功能尚未开启")
    teacher_id = body.teacher_id
    if body.conversation_id:
        conversation = _student_conversation(db, body.conversation_id, student)
        teacher_id = conversation.teacher_group_id
        from ..models import LLMGroup
        teacher = db.get(LLMGroup, teacher_id) if teacher_id else None
    else:
        teacher = _teacher(db, student, teacher_id, channel)
        teacher_id = teacher.id if teacher else None
    _check_policy(student, db, teacher_id, channel)
    if not image_chat.capabilities(db, teacher)["image_input"]:
        raise HTTPException(422, "这位老师暂不支持图片提问")
    if not _limited(db, f"image-upload:{student.id}", 15):
        raise HTTPException(429, "上传过于频繁，请稍后重试")
    media.require_storage()
    aid = uuid.uuid4().hex
    key = f"incoming/{student.id}/{aid}"
    asset = MediaAsset(id=aid, student_id=student.id, object_key=f"private/{student.id}/{aid}.jpg", upload_key=key)
    token = media.upload_token(key)
    db.add(asset)
    db.commit()
    return {"asset_id": aid, "upload_url": settings.qiniu_upload_url, "key": key, "token": token,
            "max_bytes": settings.image_max_bytes, "expires_in": 600}


@router.post("/media/{asset_id}/complete")
async def complete(asset_id: str, student: Student = Depends(current_student), db: Session = Depends(get_db)):
    if not settings.image_features_enabled:
        raise HTTPException(503, "图片功能尚未开启")
    asset = db.get(MediaAsset, asset_id)
    if not asset or asset.student_id != student.id:
        raise HTTPException(404, "图片不存在")
    if asset.status == "ready":
        return media.block(asset)
    if asset.status in ("blocked", "deleting"):
        raise HTTPException(422, "图片不可用，请重新上传")
    if not _limited(db, f"image-complete:{student.id}", 20):
        raise HTTPException(429, "操作过于频繁，请稍后重试")
    try:
        if asset.status == "uploading":
            data = await media.fetch_image(media.download_url(asset.upload_key))
            clean, width, height = await asyncio.to_thread(media.sanitize, data)
            await media.store(asset.object_key, clean)
            asset.width, asset.height, asset.byte_size = width, height, len(clean)
            asset.status = "checking"
            db.commit()
        asset.status = "ready" if await media.moderate(asset.object_key) else "blocked"
        db.commit()
        if asset.status != "ready":
            raise HTTPException(422, "图片未通过审核，请更换图片")
        return media.block(asset)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "图片上传校验或审核失败，请稍后重试")


@router.get("/media/{asset_id}")
def read(asset_id: str, authorization: str = Header(default=""), db: Session = Depends(get_db)):
    try:
        role = parse_token(authorization.removeprefix("Bearer ")).get("role")
    except Exception:
        raise HTTPException(401, "登录已失效")
    asset = db.get(MediaAsset, asset_id)
    if not asset or asset.status != "ready" or asset.student_id is None:
        raise HTTPException(404, "图片不存在或尚未通过审核")
    if role == "student":
        student = current_student(authorization, db)
        if asset.student_id != student.id:
            raise HTTPException(404, "图片不存在")
        if asset.message_id:
            message = db.get(Message, asset.message_id)
            _student_conversation(db, message.conversation_id, student)
    elif role == "guardian":
        guardian = guardian_identity(authorization, db)
        require_family_access(guardian.family_id, db)
        owner = db.get(Student, asset.student_id)
        if not owner or owner.family_id != guardian.family_id:
            raise HTTPException(404, "图片不存在")
    else:
        raise HTTPException(403, "没有访问权限")
    return {**media.block(asset), "url": media.download_url(asset.object_key), "expires_in": 300}


class DiagramIn(BaseModel):
    locale: str = "zh-Hans"


@router.post("/chat/messages/{message_id}/diagram")
def diagram(message_id: int, body: DiagramIn, student: Student = Depends(current_student),
            db: Session = Depends(get_db), channel: str = Depends(current_channel)):
    message = db.get(Message, message_id)
    if not message:
        raise HTTPException(404, "消息不存在")
    conversation = _student_conversation(db, message.conversation_id, student)
    if not _limited(db, f"image-job:{student.id}", 6):
        raise HTTPException(429, "配图请求过于频繁，请稍后重试")
    # Viewing or retrying an existing result must not consume another chat question.
    existing = db.query(ImageJob).filter_by(message_id=message.id).first()
    if existing and existing.state not in ("failed", "skipped"):
        return image_jobs.public(existing)
    _check_policy(student, db, conversation.teacher_group_id, channel, check_message_quota=False)
    from ..services.language import normalize_locale
    return image_jobs.public(image_jobs.enqueue(db, student, conversation, message,
        normalize_locale(body.locale), manual=True))


@router.get("/chat/image-jobs/{job_id}")
def job_status(job_id: int, student: Student = Depends(current_student), db: Session = Depends(get_db)):
    job = db.get(ImageJob, job_id)
    if not job or job.student_id != student.id:
        raise HTTPException(404, "图示任务不存在")
    message = db.get(Message, job.message_id)
    _student_conversation(db, message.conversation_id, student)
    return {**image_jobs.public(job), "content_blocks": message.content_blocks}


@router.get("/chat/sessions/{conversation_id}/capabilities")
def conversation_capabilities(conversation_id: int, student: Student = Depends(current_student), db: Session = Depends(get_db)):
    conversation = _student_conversation(db, conversation_id, student)
    from ..models import LLMGroup
    teacher = db.get(LLMGroup, conversation.teacher_group_id) if conversation.teacher_group_id else None
    return image_chat.capabilities(db, teacher)
