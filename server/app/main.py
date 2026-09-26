import contextlib
import os
import pathlib

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from .api import admin, auth, bind, chat, parent
from .db import Base, engine
from .config import settings
from .ratelimit import RateLimitMiddleware
from .web_page import WEB_PAGE_HTML


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.env == "prod" and (settings.jwt_secret == "change-me-in-prod" or len(settings.jwt_secret) < 32):
        raise RuntimeError("生产环境必须设置至少 32 字符的 JWT_SECRET")
    if settings.env == "prod" and any(len(token.strip()) < 32 for token in os.getenv("ADMIN_TOKENS", "").split(",") if token.strip()):
        raise RuntimeError("生产环境 ADMIN_TOKENS 中每个令牌必须至少 32 字符")
    if settings.env in ("dev", "test"):
        Base.metadata.create_all(engine)          # 开发便利；prod 走 Alembic
    else:
        from alembic import command
        from alembic.config import Config
        cfg = Config(str(pathlib.Path(__file__).resolve().parents[1] / "alembic.ini"))
        command.upgrade(cfg, "head")              # 生产启动即迁移到最新
    yield


app = FastAPI(title="ai-zhuxue API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.env != "prod" else [x.strip() for x in settings.cors_origins.split(",") if x.strip()],
    allow_methods=["*"], allow_headers=["*"],
)
app.add_middleware(RateLimitMiddleware)
app.include_router(auth.router)
app.include_router(bind.router)
app.include_router(chat.router)
app.include_router(parent.router)
app.include_router(admin.router)


@app.get("/web", response_class=HTMLResponse, include_in_schema=False)
def web_chat():
    """Web 端：仅提供聊天功能（2026-09-14 提案第四轮澄清的范围冻结）。审查/管理功能不进 web 端。"""
    return WEB_PAGE_HTML


@app.get("/health")
def health():
    return {"status": "ok", "env": settings.env, "fence_mode": settings.fence_mode,
            "llm_provider": settings.llm_provider}
