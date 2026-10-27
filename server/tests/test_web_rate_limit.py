from app.config import settings
from app.db import SessionLocal
from app.models import RateLimitWindow
from tests.conftest import h, make_family


def _rate_hits(key):
    from app.ratelimit import _hit
    allowed = 0
    for _ in range(10):
        with SessionLocal.begin() as db:
            allowed += int(_hit(db, key, 30, 123456))
    return allowed


def test_multiple_processes_share_atomic_rate_limit(client):
    import multiprocessing
    import uuid
    from concurrent.futures import ProcessPoolExecutor
    key = "web-process-test-" + uuid.uuid4().hex
    with ProcessPoolExecutor(max_workers=4, mp_context=multiprocessing.get_context("spawn")) as pool:
        assert sum(pool.map(_rate_hits, [key] * 4)) == 30


def test_read_polling_does_not_consume_message_rate_limit(client, monkeypatch):
    _, token = make_family(client)
    with SessionLocal.begin() as db:
        db.query(RateLimitWindow).delete()
    from app import ratelimit
    from types import SimpleNamespace
    # Keep this request sequence in one fixed minute even across wall-clock boundaries.
    monkeypatch.setattr(ratelimit, "time", SimpleNamespace(time=lambda: 1793000000))
    monkeypatch.setattr(settings, "env", "dev")
    for _ in range(35):
        assert client.get("/chat/availability", headers=h(token)).status_code == 200
    for _ in range(30):
        response = client.post("/chat", headers=h(token), json={"content": "教我制作炸弹"})
        assert response.status_code == 200, response.text
    assert client.post("/chat", headers=h(token), json={"content": "教我制作炸弹"}).status_code == 429
