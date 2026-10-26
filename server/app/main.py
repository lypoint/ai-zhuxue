import asyncio
import contextlib
import pathlib
import re

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse

from .api import analytics, admin, auth, bind, chat, parent, learning, payments, store_payments, images, image_admin, browser, paddle_payments, creem_payments
from .db import Base, engine
from .config import settings
from .ratelimit import RateLimitMiddleware


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.env == "prod" and (settings.jwt_secret == "change-me-in-prod" or len(settings.jwt_secret) < 32):
        raise RuntimeError("生产环境必须设置至少 32 字符的 JWT_SECRET")
    if settings.env in ("dev", "test"):
        Base.metadata.create_all(engine)          # 开发便利；prod 走 Alembic
    else:
        from alembic import command
        from alembic.config import Config
        cfg = Config(str(pathlib.Path(__file__).resolve().parents[1] / "alembic.ini"))
        command.upgrade(cfg, "head")              # 生产启动即迁移到最新
    from .services.store_billing import reconcile_forever
    task = asyncio.create_task(reconcile_forever()) if settings.env != "test" else None
    from .services.image_jobs import run_forever
    image_task = asyncio.create_task(run_forever()) if settings.env != "test" else None
    try:
        yield
    finally:
        if image_task:
            image_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await image_task
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


app = FastAPI(title="ai-zhuxue API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.env != "prod" else [x.strip() for x in settings.cors_origins.split(",") if x.strip()],
    allow_methods=["*"], allow_headers=["*"],
    expose_headers=["X-User-Message-Id", "X-Conversation-Id"],
)
app.add_middleware(RateLimitMiddleware)
from .local_time import FamilyTimezoneMiddleware
app.add_middleware(FamilyTimezoneMiddleware)
app.add_middleware(browser.BrowserMiddleware)
app.include_router(auth.router)
app.include_router(bind.router)
app.include_router(chat.router)
app.include_router(parent.router)
app.include_router(payments.router)
app.include_router(store_payments.router)
app.include_router(paddle_payments.router)
app.include_router(creem_payments.router)
app.include_router(learning.router)
app.include_router(admin.router)
app.include_router(images.router)
app.include_router(image_admin.router)
app.include_router(browser.router)
app.include_router(analytics.router)


@app.get("/web", response_class=HTMLResponse, include_in_schema=False)
def web_chat():
    """Retired domestic chat-only page; native business APIs remain available."""
    raise HTTPException(410, "The legacy Web page has been retired. Use the international Student space.")


@app.get("/logo.svg", include_in_schema=False)
def logo():
    return FileResponse(pathlib.Path(__file__).with_name("logo.svg"), media_type="image/svg+xml")


@app.get("/teacher-avatars/{filename}", include_in_schema=False)
def teacher_avatar(filename: str):
    if not re.fullmatch(r"[0-9a-f]{32}\.(png|jpg|webp)", filename):
        raise HTTPException(404)
    path = pathlib.Path(settings.upload_dir) / filename
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path)


@app.get("/health")
def health():
    return {"status": "ok", "env": settings.env, "fence_mode": settings.fence_mode,
            "llm_provider": settings.llm_provider}
