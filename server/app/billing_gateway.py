"""Restricted Google transport; subscription ownership and entitlements stay in the API."""
import asyncio
import contextlib
import hmac
import json
import re
import time
from pathlib import Path
from typing import Literal
from urllib.parse import quote, unquote

import httpx
import jwt
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field

from .config import settings


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    if len(settings.google_gateway_token) < 32 or not settings.google_package_name:
        raise RuntimeError("Google relay credentials are missing")
    app.state.service = json.loads(Path(settings.google_service_account_path).read_text())
    jwt.encode({"iss": app.state.service["client_email"]}, app.state.service["private_key"], algorithm="RS256")
    app.state.token = ""
    app.state.expires = 0
    app.state.lock = asyncio.Lock()
    async with httpx.AsyncClient(timeout=20, limits=httpx.Limits(max_connections=10, max_keepalive_connections=5)) as client:
        app.state.client = client
        yield


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
bearer = HTTPBearer(auto_error=False)


def authorize(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if credentials is None or not hmac.compare_digest(credentials.credentials.encode(), settings.google_gateway_token.encode()):
        raise HTTPException(401, "Unauthorized")


class GoogleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    method: Literal["GET", "POST"]
    path: str = Field(min_length=1, max_length=32768)
    body: dict | None = None


def allowed(body: GoogleRequest) -> bool:
    package = re.escape(quote(settings.google_package_name, safe=""))
    segment = r"([A-Za-z0-9._~%\-]+)"
    suffix = (r"subscriptionsv2/tokens/" + segment if body.method == "GET" else
              r"subscriptions/" + segment + r"/tokens/" + segment + r":acknowledge")
    match = re.fullmatch(r"applications/" + package + r"/purchases/" + suffix, body.path)
    if not match or body.body not in (None, {}):
        return False
    for value in match.groups():
        decoded = unquote(value)
        if quote(decoded, safe="") != value or "\\" in decoded or any(p in (".", "..") for p in decoded.split("/")):
            return False
    return True


async def access_token(request: Request) -> str:
    state = request.app.state
    async with state.lock:
        if time.monotonic() < state.expires:
            return state.token
        now = int(time.time())
        assertion = jwt.encode({"iss": state.service["client_email"],
            "scope": "https://www.googleapis.com/auth/androidpublisher",
            "aud": "https://oauth2.googleapis.com/token", "iat": now, "exp": now + 3600},
            state.service["private_key"], algorithm="RS256")
        response = await state.client.post("https://oauth2.googleapis.com/token", data={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion})
        response.raise_for_status()
        data = response.json()
        state.token = data["access_token"]
        state.expires = time.monotonic() + max(0, min(int(data["expires_in"]), 3600) - 60)
        return state.token


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/google/certs", dependencies=[Depends(authorize)])
async def certificates(request: Request):
    try:
        response = await request.app.state.client.get("https://www.googleapis.com/oauth2/v3/certs")
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, "Google certificates unavailable") from None


@app.post("/google/request", dependencies=[Depends(authorize)])
async def google_request(body: GoogleRequest, request: Request):
    if not allowed(body):
        raise HTTPException(403, "Operation not allowed")
    try:
        token = await access_token(request)
        response = await request.app.state.client.request(body.method,
            "https://androidpublisher.googleapis.com/androidpublisher/v3/" + body.path,
            headers={"Authorization": "Bearer " + token}, json=body.body)
        if response.status_code == 401:
            request.app.state.expires = 0
        return Response(content=response.content, status_code=response.status_code, media_type="application/json")
    except (httpx.HTTPError, ValueError, KeyError):
        raise HTTPException(502, "Google Play unavailable") from None
