import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db import SessionLocal, engine
from app.main import app
from app.models import ActiveTime, Family, MediaAsset, WebSession
from app.local_time import family_timezone, utc_bounds


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="PostgreSQL session invariant")
def test_postgresql_connections_use_utc():
    from sqlalchemy import text
    with engine.connect() as connection:
        assert connection.scalar(text("SHOW TIME ZONE")) == "UTC"


@pytest.fixture
def web(client, monkeypatch):
    from app.api import auth
    monkeypatch.setattr(settings, "web_enabled", True)
    monkeypatch.setattr(auth, "verify_google_identity", lambda _: {"sub": "web-" + uuid.uuid4().hex})
    client.cookies.clear()
    result = client.post("/browser/parent/login", json={"id_token": "test-google-token-for-browser"},
                         headers={"Origin": settings.web_parent_origin})
    assert result.status_code == 200, result.text
    csrf = result.json()["csrf_token"]
    headers = {"Origin": settings.web_parent_origin, "X-CSRF-Token": csrf}
    assert client.put("/browser/parent/api/parent/timezone", headers=headers, json={"timezone": "UTC"}).status_code == 200
    return client, headers


def child_and_session(client, headers):
    created = client.post("/browser/parent/api/parent/students", json={"nickname": "Jamie"}, headers=headers)
    assert created.status_code == 200, created.text
    result = client.post("/browser/student/connect", headers={"Origin": settings.web_student_origin}, json={
        "bind_code": created.json()["bind_code"], "installation_id": "browser-" + uuid.uuid4().hex})
    assert result.status_code == 200, result.text
    return created.json()["student_id"], {"Origin": settings.web_student_origin, "X-CSRF-Token": result.json()["csrf_token"]}


def test_parent_login_distinguishes_signup_from_returning_login(client, monkeypatch):
    from app.api import auth
    monkeypatch.setattr(settings, "web_enabled", True)
    subject = "analytics-" + uuid.uuid4().hex
    monkeypatch.setattr(auth, "verify_google_identity", lambda _: {"sub": subject})
    for expected in [True, False]:
        response = client.post('/browser/parent/login', headers={'Origin': settings.web_parent_origin},
                               json={'id_token': 'synthetic-google-token-for-analytics'})
        assert response.status_code == 200, response.text
        assert response.json()['is_new_user'] is expected
        assert set(response.json()) == {'csrf_token', 'role', 'is_new_user'}


def test_browser_cookie_csrf_origins_role_and_no_payments(web):
    client, headers = web
    cookie = client.cookies.get("ailearning-parent")
    with SessionLocal() as db:
        assert db.get(WebSession, hashlib.sha256(cookie.encode()).hexdigest())
        assert db.get(WebSession, cookie) is None
    session = client.get("/browser/parent/session").json()
    assert "token" not in session
    assert client.put("/browser/parent/api/parent/guardian/nickname", json={"nickname": "Alex"}).status_code == 403
    assert client.get("/browser/parent/session", headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post("/browser/parent/api/parent/subscription/pay", headers=headers, json={}).status_code == 403
    assert client.get("/browser/parent/api/admin/families").status_code == 403
    sid, student_headers = child_and_session(client, headers)
    assert client.get("/browser/student/api/parent/family").status_code == 403
    assert client.get("/browser/student/api/chat/my-stats").status_code == 200
    assert client.post("/browser/student/api/chat/heartbeat", headers=student_headers, json={"seconds": 120}).status_code == 403
    assert client.get("/browser/parent/api/parent/family").json()["students"][0]["id"] == sid


def test_web_logout_only_revokes_current_browser_and_rebind_revokes_student(web):
    client, headers = web
    sid, student_headers = child_and_session(client, headers)
    old_parent = client.cookies.get("ailearning-parent")
    assert client.post("/browser/parent/logout", headers=headers).status_code == 200
    assert client.get("/browser/parent/session").status_code == 401
    assert client.get("/browser/student/session").status_code == 200
    with SessionLocal() as db:
        assert db.get(WebSession, hashlib.sha256(old_parent.encode()).hexdigest()) is None
        row = db.query(WebSession).filter_by(role="student", subject_id=sid).one()
        family_id = row.family_id
        from app.models import Guardian
        guardian = db.query(Guardian).filter_by(family_id=family_id).one()
        from app.security import make_token
        native = make_token("guardian", guardian.id, family_id, guardian.token_version)
    code = client.post(f"/parent/students/{sid}/rebind-code", headers={"Authorization": "Bearer " + native}).json()["bind_code"]
    result = client.post("/auth/student/login", json={"bind_code": code, "installation_id": "another-" + uuid.uuid4().hex})
    assert result.status_code == 200
    assert client.get("/browser/student/session").status_code == 401


def test_family_timezone_dst_and_usage_carry(web):
    client, headers = web
    sid, _ = child_and_session(client, headers)
    client.post("/chat/heartbeat", json={}, headers={})  # An unauthenticated caller cannot affect usage.
    with SessionLocal.begin() as db:
        db.add(ActiveTime(student_id=sid, day=datetime.now(timezone.utc).date().isoformat(), seconds=180))
    with SessionLocal.begin() as db:
        family = db.query(Family).filter_by(timezone="UTC").order_by(Family.id.desc()).first()
        family.timezone_changed_at = datetime.now(timezone.utc) - timedelta(days=2)
    response = client.put("/browser/parent/api/parent/timezone", headers=headers, json={"timezone": "America/New_York"})
    assert response.status_code == 200, response.text
    assert client.get("/browser/student/api/chat/availability").json()["used_seconds"] == 180
    with SessionLocal() as db:
        assert db.query(ActiveTime).filter_by(student_id=sid).count() == 1
        assert sum(row.seconds for row in db.query(ActiveTime).filter_by(student_id=sid)) == 180
    assert client.put("/browser/parent/api/parent/timezone", headers=headers, json={"timezone": "Europe/Berlin"}).status_code == 409
    assert client.put("/browser/parent/api/parent/timezone", headers=headers, json={"timezone": "not-a-zone"}).status_code == 422
    marker = family_timezone.set("America/New_York")
    try:
        start, end = utc_bounds("2026-03-08")
        assert (end - start).total_seconds() == 23 * 3600
        start, end = utc_bounds("2026-11-01")
        assert (end - start).total_seconds() == 25 * 3600
    finally:
        family_timezone.reset(marker)


def test_browser_heartbeat_uses_elapsed_wall_time_across_tabs(web):
    client, headers = web
    sid, student_headers = child_and_session(client, headers)
    with SessionLocal.begin() as db:
        row = db.query(WebSession).filter_by(role="student", subject_id=sid).one()
        row.heartbeat_at = datetime.now(timezone.utc) - timedelta(seconds=30)
    first = client.post("/browser/student/heartbeat", headers=student_headers, json={"seconds": 30})
    assert first.status_code == 200, first.text
    assert first.json()["total_seconds"] == 30
    second = client.post("/browser/student/heartbeat", headers=student_headers, json={"seconds": 30})
    assert second.json()["total_seconds"] == 30
    assert client.post("/browser/student/heartbeat", headers=student_headers, json={"seconds": 120}).status_code == 422


def test_concurrent_browser_heartbeats_do_not_duplicate_usage(web, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from app.api import browser
    client, headers = web
    sid, student_headers = child_and_session(client, headers)
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(browser, "utcnow", lambda: now)
    with SessionLocal.begin() as db:
        row = db.query(WebSession).filter_by(role="student", subject_id=sid).one()
        row.heartbeat_at = now - timedelta(seconds=30)
    cookie = client.cookies.get("ailearning-student")
    barrier = Barrier(4)

    def post(_):
        tab = TestClient(app)
        tab.cookies.set("ailearning-student", cookie)
        barrier.wait(timeout=10)
        return tab.post("/browser/student/heartbeat", headers=student_headers, json={"seconds": 30})

    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(post, range(4)))
    assert all(response.status_code == 200 for response in responses)
    with SessionLocal() as db:
        assert sum(row.seconds for row in db.query(ActiveTime).filter_by(student_id=sid)) == 30


def test_private_media_is_same_origin_and_owner_checked(web, monkeypatch):
    from app.services import media
    client, headers = web
    sid, _ = child_and_session(client, headers)
    aid = uuid.uuid4().hex
    with SessionLocal.begin() as db:
        db.add(MediaAsset(id=aid, student_id=sid, object_key="private/example.jpg", status="ready"))
    signed_urls = []
    fetched_urls = []
    fail_download = False
    def download_url(_):
        url = f"https://private-storage.example/signed?generation={len(signed_urls)}"
        signed_urls.append(url)
        return url
    monkeypatch.setattr(media, "download_url", download_url)
    async def fetch_image(url):
        fetched_urls.append(url)
        if fail_download:
            raise RuntimeError("Upstream signed resource expired")
        return b"reviewed-jpeg"
    monkeypatch.setattr(media, "fetch_image", fetch_image)
    result = client.get(f"/browser/student/media/{aid}")
    assert result.content == b"reviewed-jpeg"
    assert result.headers["content-type"] == "image/jpeg"
    assert "no-store" in result.headers["cache-control"]
    assert "location" not in result.headers
    assert client.get(f"/browser/parent/media/{aid}").status_code == 200
    fail_download = True
    assert client.get(f"/browser/student/media/{aid}").status_code == 503
    fail_download = False
    assert client.get(f"/browser/student/media/{aid}?v=1").content == b"reviewed-jpeg"
    assert len(set(fetched_urls)) == 4
    assert fetched_urls == signed_urls
    other = TestClient(app)
    login = other.post("/browser/parent/login", headers={"Origin": settings.web_parent_origin}, json={"id_token": "other-google-token-long-enough"})
    assert login.status_code == 200
    assert other.get(f"/browser/parent/media/{aid}").status_code == 404


def test_browser_disabled_and_legacy_gone(client, monkeypatch):
    monkeypatch.setattr(settings, "web_enabled", False)
    assert client.get("/browser/parent/config").status_code == 404
    assert client.get("/web").status_code == 410


def test_production_cookie_and_host_isolation(web, monkeypatch):
    monkeypatch.setattr(settings, "env", "prod")
    monkeypatch.setattr(settings, "web_parent_origin", "https://parents.example")
    monkeypatch.setattr(settings, "web_student_origin", "https://learn.example")
    parent = TestClient(app, base_url="https://parents.example")
    response = parent.post("/browser/parent/login", headers={"Origin": "https://parents.example"},
                           json={"id_token": "test-production-cookie-identity"})
    assert response.status_code == 200, response.text
    header = response.headers["set-cookie"].lower()
    assert "__host-ailearning-parent=" in header
    assert "secure" in header and "httponly" in header and "samesite=strict" in header
    assert "domain=" not in header
    assert parent.get("/browser/parent/session").status_code == 200
    assert parent.get("https://learn.example/browser/parent/session").status_code == 403


def test_student_connect_requires_timezone_confirmation(web):
    client, _ = web
    login = client.post("/browser/parent/login", headers={"Origin": settings.web_parent_origin},
                        json={"id_token": "another-new-google-family-identity"}).json()
    parent_headers = {"Origin": settings.web_parent_origin, "X-CSRF-Token": login["csrf_token"]}
    created = client.post("/browser/parent/api/parent/students", headers=parent_headers, json={"nickname": "Jamie"}).json()
    payload = {"bind_code": created["bind_code"], "installation_id": "pending-timezone-" + uuid.uuid4().hex}
    assert client.post("/browser/student/connect", headers={"Origin": settings.web_student_origin}, json=payload).status_code == 409
    client.put("/browser/parent/api/parent/timezone", headers=parent_headers, json={"timezone": "UTC"})
    assert client.post("/browser/student/connect", headers={"Origin": settings.web_student_origin}, json=payload).status_code == 200


def test_expired_session_and_logout_all_revoke_access(web, monkeypatch):
    from app.api import auth
    from app.models import Guardian
    client, headers = web
    sid, _ = child_and_session(client, headers)
    with SessionLocal.begin() as db:
        row = db.query(WebSession).filter_by(role="student", subject_id=sid).one()
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert client.get("/browser/student/session").status_code == 401
    assert client.get("/browser/student/api/chat/my-stats").status_code == 401
    cookie = client.cookies.get("ailearning-parent")
    with SessionLocal() as db:
        session = db.get(WebSession, hashlib.sha256(cookie.encode()).hexdigest())
        google_sub = db.get(Guardian, session.subject_id).google_sub
    monkeypatch.setattr(auth, "verify_google_identity", lambda _: {"sub": google_sub})
    other = TestClient(app)
    response = other.post("/browser/parent/login", headers={"Origin": settings.web_parent_origin},
                          json={"id_token": "second-browser-same-google-identity"})
    assert response.status_code == 200
    assert other.cookies.get("ailearning-parent") != cookie
    assert other.get("/browser/parent/session").status_code == 200
    assert client.post("/browser/parent/logout-all", headers=headers).status_code == 200
    assert other.get("/browser/parent/session").status_code == 401
