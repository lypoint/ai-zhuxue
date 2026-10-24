"""Loopback-only E2E harness: real API/SQLite, deterministic external identity, models and media.

Never import this module from the production app. No real account, model or payment service is called.
"""
import os
import tempfile

https_gateway = os.environ.get("WEB_ACCEPTANCE_HTTPS") == "1"
os.environ["ENV"] = "prod" if https_gateway else "test"
os.environ["DATABASE_URL"] = "sqlite:///" + (os.environ.get("WEB_ACCEPTANCE_TMP") or tempfile.mkdtemp(prefix="ai-web-e2e-")) + "/test.db"
os.environ["JWT_SECRET"] = "web-acceptance-only-secret-not-for-production"
os.environ["FENCE_MODE"] = "heuristic"
os.environ["FENCE_QUIET_ENABLED"] = "false"
os.environ["WEB_ENABLED"] = "true"
os.environ["WEB_PARENT_ORIGIN"] = "https://localhost:18443" if https_gateway else "http://localhost:5173"
os.environ["WEB_STUDENT_ORIGIN"] = "https://127.0.0.1:19443" if https_gateway else "http://localhost:5174"
os.environ["GOOGLE_LOGIN_CLIENT_ID"] = "acceptance-only.apps.googleusercontent.com"
os.environ["IMAGE_FEATURES_ENABLED"] = "true"
os.environ["QINIU_ACCESS_KEY"] = "acceptance-only"
os.environ["QINIU_SECRET_KEY"] = "acceptance-only"
os.environ["QINIU_BUCKET"] = "acceptance-only"
os.environ["QINIU_DOMAIN"] = "https://acceptance-storage.invalid"

import asyncio
import io
import json
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

import uvicorn
from fastapi import HTTPException
from PIL import Image

from app.main import app, lifespan
from app.db import Base, engine, SessionLocal
from app.models import LLMGroup, ChannelTeacherDefault, ImageJob, MediaAsset, Message, Conversation, Notification, Student
from app.api import auth, chat
from app.services import image_models, media, image_jobs, llm


if https_gateway:
    @asynccontextmanager
    async def fixture_lifespan(_):
        # The isolated schema is created below; real migration/startup is covered separately.
        # Keep browser production security enabled without starting external-service workers.
        yield
    app.router.lifespan_context = fixture_lifespan

storage = {}


def identity(token):
    if not token.startswith("acceptance-google-"):
        raise HTTPException(401, "Invalid acceptance token")
    return {"sub": token.removeprefix("acceptance-google-")}


async def model_stream(messages, **kwargs):
    prompt = str(messages[-1]["content"])
    key = (kwargs.get("family_id"), prompt)
    if "NOTIFICATION_PAGINATION" in prompt:
        with SessionLocal.begin() as db:
            conversation = (db.query(Conversation).join(Student, Conversation.student_id == Student.id)
                            .filter(Student.family_id == kwargs["family_id"])
                            .order_by(Conversation.id.desc()).first())
            for number in range(21):
                db.add(Notification(family_id=kwargs["family_id"], type="system",
                    title=f"Learning update {number + 1}", body="Review the source learning conversation.",
                    conversation_id=conversation.id))
    if "FAIL_ONCE" in prompt and key not in failed:
        failed.add(key)
        raise llm.LLMUnavailable("Temporary model failure. Please retry.")
    answer = "Great question. In **math**, start with equal-sized pieces.\n\n$\\frac{1}{2}+\\frac{1}{4}=\\frac{3}{4}$\n\nAlso \\(7 \\times 8 = 56\\).\n\n\\[x+y=3\\]\n\n```text\n\\(keep this as code\\)\n```\n\nWhat do you notice about the denominator?"
    if "SLOW_RESPONSE" in prompt:
        await asyncio.sleep(3)
    for start in range(0, len(answer), 16):
        await asyncio.sleep(.03)
        yield {"delta": answer[start:start + 16], "provider": "acceptance", "model": "fixture"}
    yield {"usage": {"tokens_in": 12, "tokens_out": 30}}


failed = set()


async def store(key, data):
    storage[key] = data


async def fetch(url):
    key = urlsplit(url).path.lstrip("/")
    if key not in storage:
        raise HTTPException(404, "Image not found")
    return storage[key]


async def moderate(_):
    return True


async def vision(*args, **kwargs):
    return {"content": json.dumps({"text": "Explain the math fraction 1/2 + 1/4", "relations": "Equal pieces", "uncertain": ""}), "tokens_in": 1, "tokens_out": 1, "provider": "acceptance", "model": "vision-fixture"}


async def diagram(db, student, conversation, message, locale="en", **kwargs):
    pass


def enqueue(db, student, conversation, message, locale="en", **kwargs):
    from app.models import utcnow
    existing = db.query(ImageJob).filter_by(message_id=message.id).first()
    if existing:
        return existing
    deferred = db.query(Message.id).filter(Message.conversation_id == conversation.id,
        Message.role == "user", Message.content.contains("ASYNC_DIAGRAM")).first() is not None
    image = Image.new("RGB", (480, 180), "#edf1e7")
    output = io.BytesIO(); image.save(output, "JPEG")
    import uuid
    aid = uuid.uuid4().hex
    key = f"private/{student.id}/{aid}.jpg"
    storage[key] = output.getvalue()
    asset = MediaAsset(id=aid, student_id=student.id, message_id=message.id, object_key=key, status="ready", width=480, height=180)
    db.add(asset)
    job = ImageJob(message_id=message.id, student_id=student.id, teacher_id=conversation.teacher_group_id,
                   state="queued" if deferred else "ready", asset_id=None if deferred else aid,
                   snapshot_json="{}", finished_at=None if deferred else utcnow())
    db.add(job)
    blocks = json.dumps([{"type": "image", "asset_id": aid, "width": 480, "height": 180, "caption": "Math diagram"}])
    if not deferred:
        message.blocks_json = blocks
    db.commit()
    if deferred:
        from threading import Timer
        job_id, message_id = job.id, message.id
        def finish():
            with SessionLocal.begin() as next_db:
                pending = next_db.get(ImageJob, job_id)
                pending.state, pending.asset_id, pending.finished_at = "ready", aid, utcnow()
                next_db.get(Message, message_id).blocks_json = blocks
        timer = Timer(4, finish)
        timer.daemon = True
        timer.start()
    return job


auth.verify_google_identity = identity
chat.llm.chat_stream = model_stream
media.store = store
media.fetch_image = fetch
media.moderate = moderate
media.download_url = lambda key, **kwargs: "https://acceptance-storage.invalid/" + key
image_models.complete = vision
image_jobs.enqueue = enqueue

Base.metadata.create_all(engine)
with SessionLocal.begin() as db:
    teacher = LLMGroup(name="web-acceptance", provider="glm", chat_model="fixture", fence_model="fixture",
        api_key="acceptance-only-not-a-real-key", teacher_name="Learning guide", teacher_channel="googleplay",
        teacher_enabled=True, is_active=True, image_input_mode="native", diagram_enabled=True)
    db.add(teacher); db.flush()
    teacher_id = teacher.id
    db.add(ChannelTeacherDefault(channel="googleplay", teacher_group_id=teacher_id))
    db.add(LLMGroup(name="web-acceptance-text", provider="glm", chat_model="fixture", fence_model="fixture",
        api_key="acceptance-only-not-a-real-key", teacher_name="Text guide", teacher_channel="googleplay",
        teacher_enabled=True, is_active=False, image_input_mode="off", diagram_enabled=False))
    db.add(LLMGroup(name="web-acceptance-custom-name", provider="glm", chat_model="fixture", fence_model="fixture",
        api_key="acceptance-only-not-a-real-key", teacher_name="自定义导师", teacher_channel="googleplay",
        teacher_enabled=True, is_active=False, image_input_mode="off", diagram_enabled=False))
with SessionLocal.begin() as db:
    teacher = db.get(LLMGroup, teacher_id)
    teacher.vision_test_signature = image_models.signature(image_models.native_snapshot(teacher_id))

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8810, log_level="warning")
