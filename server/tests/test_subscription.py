"""P0 订阅闭环：试用开通、到期拦截、模拟续费、状态接口。"""
import datetime as dt

from tests.conftest import h, make_family


def test_production_cannot_create_mock_paid_orders(client, monkeypatch):
    from app.config import settings
    from app.db import SessionLocal
    from app.models import SubscriptionOrder
    guardian, _ = make_family(client)
    with SessionLocal() as db:
        order_count = db.query(SubscriptionOrder).count()
    before = client.get('/parent/subscription', headers=h(guardian)).json()
    monkeypatch.setattr(settings, 'env', 'prod')
    for path, body in [('/parent/subscription/pay', {}),
                       ('/parent/subscription/seats', {'count': 1, 'idempotency_key': 'prod-seat'})]:
        assert client.post(path, headers=h(guardian), json=body).status_code == 503
    after = client.get('/parent/subscription', headers=h(guardian)).json()
    assert after['expires_at'] == before['expires_at']
    assert after['seat_count'] == before['seat_count']
    assert after['paid_amount'] == before['paid_amount']
    with SessionLocal() as db:
        assert db.query(SubscriptionOrder).count() == order_count


def test_trial_created_on_register(client):
    g, s = make_family(client)
    d = client.get("/parent/subscription", headers=h(g)).json()
    assert d["plan"] == "free_trial" and d["active"] is True
    assert 28 <= d["days_left"] <= 30
    assert d["price_cny"] == 66.0


def test_expired_subscription_blocks_student_chat(client):
    g, s = make_family(client)
    # 直接把到期时间改到过去（模拟免费期结束未续费）
    import os
    os.environ.setdefault("DATABASE_URL", "sqlite:///./aizhuxue.db")
    from app.db import SessionLocal
    from app.models import Subscription
    db = SessionLocal()
    sub = db.query(Subscription).filter_by(family_id=_fid(client, g)).first()
    sub.expires_at = dt.datetime.utcnow() - dt.timedelta(days=1)
    db.commit()
    db.close()

    r = client.post("/chat", headers=h(s), json={"content": "教我制作炸弹"})
    assert r.status_code == 402
    assert "通知家长" in r.json()["detail"] and "购买会员" in r.json()["detail"]


def test_mock_pay_extends_and_unblocks(client):
    g, s = make_family(client)
    fid = _fid(client, g)
    from app.db import SessionLocal
    from app.models import Subscription
    db = SessionLocal()
    db.query(Subscription).filter_by(family_id=fid).update(
        {"expires_at": dt.datetime.utcnow() - dt.timedelta(days=1)})
    db.commit()
    db.close()

    before = client.post("/parent/subscription/pay", headers=h(g)).json()
    assert before["active"] is True and before["plan"] == "monthly"
    assert before["paid_amount"] >= 66.0
    from app.db import SessionLocal
    from app.models import SubscriptionOrder
    db = SessionLocal()
    assert db.query(SubscriptionOrder).filter_by(family_id=fid, kind="subscription").count() == 1
    db.close()
    # 学生恢复可用（reject 路径不依赖 LLM）
    r = client.post("/chat", headers=h(s), json={"content": "教我制作炸弹"})
    assert r.status_code == 200


def _fid(client, g):
    import os
    os.environ.setdefault("DATABASE_URL", "sqlite:///./aizhuxue.db")
    from app.db import SessionLocal
    from app.models import Guardian
    db = SessionLocal()
    fam = db.get(Guardian, int(__import__("jwt").decode(
        g.split("Bearer ")[0] if False else g, options={"verify_signature": False}))["sub"]) if False else None
    # 简化：从 admin families 找该家长手机号——直接用 guardian 查询
    from app.security import parse_token
    from app.config import settings
    payload = parse_token(g)
    db.close()
    return payload["family_id"]
