"""Opaque browser sessions and a role-restricted adapter for the existing APIs."""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from ..config import settings
from ..db import get_db, SessionLocal
from ..models import BindCode, Family, Guardian, Student, WebSession, utcnow
from ..security import make_token, parse_token
from ..local_time import as_utc
from . import auth
from .deps import current_student, guardian_identity, require_family_access

router = APIRouter(prefix="/browser", tags=["browser"])


def cookie_name(role):
    return ("__Host-" if settings.env == "prod" else "") + "ailearning-" + role


def csrf(secret):
    return hmac.new(settings.jwt_secret.encode(), ("csrf:" + secret).encode(), hashlib.sha256).hexdigest()


def expected_origin(role):
    return settings.web_parent_origin if role == "parent" else settings.web_student_origin


def _session(secret, role, db):
    row = db.get(WebSession, hashlib.sha256(secret.encode()).hexdigest()) if secret else None
    if not row or row.role != role or as_utc(row.expires_at) <= utcnow():
        raise HTTPException(401, "Your session has expired. Please sign in again.")
    token = make_token("guardian" if role == "parent" else "student", row.subject_id,
                       row.family_id, row.token_version, row.device_id)
    if role == "parent":
        identity = guardian_identity("Bearer " + token, db)
        require_family_access(identity.family_id, db)
    else:
        identity = current_student("Bearer " + token, db)
    return row, token, identity


def require_session(request: Request, role: str, db: Session):
    return _session(request.cookies.get(cookie_name(role), ""), role, db)


def issue(result, role, response, db):
    payload = parse_token(result.token if hasattr(result, "token") else result["token"])
    secret = secrets.token_urlsafe(32)
    db.query(WebSession).filter(WebSession.expires_at < utcnow()).delete(synchronize_session=False)
    row = WebSession(id=hashlib.sha256(secret.encode()).hexdigest(), role=role,
        subject_id=int(payload["sub"]), family_id=payload["family_id"], token_version=payload["ver"],
        device_id=payload.get("device_id"), expires_at=utcnow() + timedelta(hours=settings.web_session_hours),
        heartbeat_at=utcnow())
    db.add(row)
    db.commit()
    response.set_cookie(cookie_name(role), secret, max_age=settings.web_session_hours * 3600,
                        httponly=True, secure=settings.env == "prod", samesite="strict", path="/")
    return {"csrf_token": csrf(secret), "role": role}


@router.get("/{role}/config")
def config(role: str):
    if role not in ("parent", "student"):
        raise HTTPException(404)
    return {"role": role, "channel": "googleplay", "market": "international",
            "google_client_id": settings.google_login_client_id if role == "parent" else "",
            "payments_enabled": (settings.paddle_sandbox_enabled or settings.creem_test_enabled) if role == "parent" else False}


@router.post("/parent/login")
async def login(body: auth.GuardianGoogleIn, response: Response, db: Session = Depends(get_db)):
    result = await auth.guardian_google(body, db, "googleplay")
    return issue(result, "parent", response, db)


class ConnectIn(BaseModel):
    bind_code: str = Field(pattern=r"^[0-9A-F]{8}$")
    installation_id: str = Field(min_length=8, max_length=64)
    device_name: str = Field(default="Web browser", max_length=100)


@router.post("/student/connect")
def connect(body: ConnectIn, response: Response, db: Session = Depends(get_db)):
    code = db.query(BindCode).filter_by(code=body.bind_code).first()
    family = db.get(Family, code.family_id) if code else None
    if family and not family.timezone:
        raise HTTPException(409, "Ask your parent to confirm the family time zone before connecting.")
    result = auth.student_login(auth.StudentLoginIn(**body.model_dump()), db)
    return {**issue(result, "student", response, db), "replaced_device_count": result["replaced_device_count"]}


@router.get("/{role}/session")
def session(role: str, request: Request, db: Session = Depends(get_db)):
    row, _, identity = require_session(request, role, db)
    family = db.get(Family, row.family_id)
    return {"role": role, "id": identity.id, "nickname": identity.nickname,
            "family_id": row.family_id, "timezone": family.timezone,
            "grade_band": getattr(identity, "grade_band", None),
            "csrf_token": csrf(request.cookies[cookie_name(role)]),
            "expires_at": row.expires_at.isoformat()}


@router.post("/{role}/logout")
def logout(role: str, request: Request, response: Response, db: Session = Depends(get_db)):
    row, _, _ = require_session(request, role, db)
    db.delete(row)
    db.commit()
    response.delete_cookie(cookie_name(role), path="/", secure=settings.env == "prod", httponly=True, samesite="strict")
    return {"ok": True}


@router.post("/{role}/logout-all")
def logout_all(role: str, request: Request, response: Response, db: Session = Depends(get_db)):
    row, _, identity = require_session(request, role, db)
    identity.token_version += 1
    db.query(WebSession).filter_by(role=role, subject_id=identity.id).delete(synchronize_session=False)
    db.commit()
    response.delete_cookie(cookie_name(role), path="/", secure=settings.env == "prod", httponly=True, samesite="strict")
    return {"ok": True}


class HeartbeatIn(BaseModel):
    seconds: int = Field(ge=0, le=90, strict=True)


@router.post("/student/heartbeat")
def heartbeat(body: HeartbeatIn, request: Request, db: Session = Depends(get_db)):
    from ..models import ActiveTime
    from ..local_time import local_now, utc_bounds
    row, _, student = require_session(request, "student", db)
    # A shared cookie identifies all tabs. Serialize elapsed-time accounting so two tabs cannot double count.
    db.query(WebSession).filter_by(id=row.id).update({WebSession.id: WebSession.id})
    db.query(Student).filter_by(id=student.id).update({Student.id: Student.id})
    row = db.query(WebSession).filter_by(id=row.id).populate_existing().with_for_update().one()
    now = utcnow()
    elapsed = max(0, min(body.seconds, 90, int((now - as_utc(row.heartbeat_at or now)).total_seconds())))
    day = local_now().date().isoformat()
    midnight = utc_bounds(day)[0].replace(tzinfo=timezone.utc)
    current = min(elapsed, max(0, int((now - midnight).total_seconds())))
    buckets = [(day, current)]
    if elapsed > current:
        buckets.append(((local_now().date() - timedelta(days=1)).isoformat(), elapsed - current))
    for key, seconds in buckets:
        active = db.query(ActiveTime).filter_by(student_id=student.id, day=key).first()
        if not active:
            active = ActiveTime(student_id=student.id, day=key, seconds=0)
            db.add(active)
        active.seconds = min(active.seconds + seconds, 480 * 60)
    row.heartbeat_at = now
    db.commit()
    total = db.query(ActiveTime).filter_by(student_id=student.id, day=day).one().seconds
    return {"day": day, "total_seconds": total}


@router.post("/student/upload")
async def upload_image(request: Request, conversation_id: int | None = None,
                       teacher_id: int | None = None, db: Session = Depends(get_db)):
    from . import images
    from ..models import MediaAsset
    from ..services import media
    _, _, student = require_session(request, "student", db)
    upload = images.upload(images.UploadIn(conversation_id=conversation_id, teacher_id=teacher_id), student, db, "googleplay")
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > settings.image_max_bytes:
            raise HTTPException(413, "The image is too large.")
    clean, width, height = await run_in_threadpool(media.sanitize, bytes(data))
    asset = db.get(MediaAsset, upload["asset_id"])
    asset.width, asset.height, asset.byte_size = width, height, len(clean)
    asset.status = "checking"
    db.commit()
    try:
        await media.store(asset.object_key, clean)
        asset.status = "ready" if await media.moderate(asset.object_key) else "blocked"
        db.commit()
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "Image storage or review is unavailable. Please retry.") from None
    if asset.status != "ready":
        raise HTTPException(422, "The image did not pass review. Please choose another.")
    return media.block(asset)


@router.get("/{role}/media/{asset_id}")
async def read_image(role: str, asset_id: str, request: Request, db: Session = Depends(get_db)):
    from . import images
    from ..services import media
    _, token, _ = require_session(request, role, db)
    result = images.read(asset_id, "Bearer " + token, db)
    try:
        data = await media.fetch_image(result["url"])
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "The image could not be loaded. Please retry.") from None
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "private, no-store"})


class BrowserMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith("/browser/"):
            return await self.app(scope, receive, send)
        request = Request(scope)
        parts = scope["path"].split("/", 3)
        role = parts[2] if len(parts) > 2 else ""
        action = parts[3] if len(parts) > 3 else ""
        async def reject(status, message):
            return await JSONResponse({"detail": message}, status)(scope, receive, send)
        if not settings.web_enabled or role not in ("parent", "student"):
            return await reject(404, "Web access is unavailable.")
        origin = request.headers.get("origin")
        expected = expected_origin(role)
        if settings.env == "prod" and request.headers.get("host") != urlsplit(expected).netloc:
            return await reject(403, "This Web space is not served on this host.")
        if settings.env == "prod" and (urlsplit(expected).scheme != "https" or
                                      settings.web_parent_origin == settings.web_student_origin):
            return await reject(503, "Web origins must be configured independently with HTTPS.")
        if origin and origin != expected:
            return await reject(403, "Origin is not allowed.")
        if request.headers.get("sec-fetch-site") == "cross-site":
            return await reject(403, "Cross-site access is not allowed.")
        unsafe = request.method not in ("GET", "HEAD", "OPTIONS")
        if unsafe and origin != expected:
            return await reject(403, "A trusted Origin is required.")
        public = action == "config" and request.method == "GET" or (
            action == ("login" if role == "parent" else "connect") and request.method == "POST")
        token = None
        if not public:
            secret = request.cookies.get(cookie_name(role), "")
            if unsafe and not secrets.compare_digest(request.headers.get("x-csrf-token", "").encode(), csrf(secret).encode()):
                return await reject(403, "Your request could not be verified. Refresh and try again.")
            def resolve():
                with SessionLocal() as db:
                    return _session(secret, role, db)[1]
            try:
                token = await run_in_threadpool(resolve)
            except HTTPException as exc:
                return await reject(exc.status_code, exc.detail)
        if action.startswith("api/"):
            path = "/" + action[4:]
            allowed = (path.startswith(("/parent/", "/bind/", "/teacher-avatars/")) if role == "parent"
                       else path == "/chat" or path.startswith(("/chat/", "/media/"))
                       or path == "/auth/student/account/delete")
            if role == "student" and path.startswith("/teacher-avatars/") and request.method == "GET":
                allowed = True
            if path.startswith("/media/"):
                allowed = False
            if path == "/chat/heartbeat":
                allowed = False
            if not allowed or path.startswith(("/parent/subscription/pay", "/parent/subscription/seats")):
                return await reject(403, "This API is unavailable in this Web space.")
            scope = {**scope, "path": path, "raw_path": path.encode()}
        scope["headers"] = [(k, v) for k, v in scope.get("headers", [])
                            if k.lower() not in (b"authorization", b"x-app-channel")]
        scope["headers"].append((b"x-app-channel", b"googleplay"))
        if token:
            scope["headers"].append((b"authorization", ("Bearer " + token).encode()))
        scope["state"] = {**scope.get("state", {}), "browser_role": role}
        async def secure_send(message):
            if message["type"] == "http.response.start":
                message["headers"] = [*message.get("headers", []),
                    (b"cache-control", b"no-store"), (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"no-referrer")]
            await send(message)
        await self.app(scope, receive, secure_send)
