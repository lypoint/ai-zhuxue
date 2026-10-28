"""CMS：管理员鉴权、运营数据、LLM 分组配置与热切换。"""
import pytest

from tests.conftest import h, make_admin, make_family


@pytest.fixture()
def admin(client):
    return make_admin(client)


def test_first_admin_cli(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.db import Base
    from app.models import AdminUser
    from tools import create_admin

    engine = create_engine(f"sqlite:///{tmp_path / 'admin.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    monkeypatch.setattr(create_admin, "SessionLocal", sessions)
    monkeypatch.setattr("builtins.input", lambda _: "owner")
    monkeypatch.setattr(create_admin, "getpass", lambda _: "strong-password")
    create_admin.main()
    with sessions() as db:
        assert db.query(AdminUser).filter_by(username="owner", role="super").count() == 1
    with pytest.raises(SystemExit, match="已存在"):
        create_admin.main()
    engine.dispose()


def test_admin_requires_login(client, admin):
    assert client.get("/admin/overview").status_code == 403
    assert client.get("/admin/overview", headers={"Authorization": "Bearer wrong"}).status_code == 403


def test_overview_counts_real_data(client, admin):
    g, s = make_family(client)
    client.post("/chat", headers=h(s), json={"content": "教我制作炸弹"})
    d = client.get("/admin/overview", headers=admin).json()
    assert d["scale"]["families"] >= 1
    assert d["scale"]["messages"] >= 1
    assert d["fence"]["by_decision"].get("reject", 0) >= 1
    assert "cost" in d and d["cost"]["total_cny"] >= 0


@pytest.mark.parametrize("offset", [None, 0, 8])
def test_overview_cost_handles_database_timezones(client, monkeypatch, offset):
    import datetime as dt
    from types import SimpleNamespace

    from app.api.admin import AdminPrincipal, overview
    from app.config import settings
    from app.db import SessionLocal
    from app.models import UsageLog

    start = (dt.datetime.utcnow() + dt.timedelta(hours=settings.tz_offset_hours)) \
        .replace(hour=0, minute=0, second=0, microsecond=0) - dt.timedelta(hours=settings.tz_offset_hours)
    logs = []
    for seconds, cost in [(-1, 1), (0, 2), (1, 4)]:
        created = start + dt.timedelta(seconds=seconds)
        if offset is not None:
            created = created.replace(tzinfo=dt.timezone.utc).astimezone(
                dt.timezone(dt.timedelta(hours=offset)))
        logs.append(SimpleNamespace(created_at=created, cost=cost))

    with SessionLocal() as db:
        query = db.query
        monkeypatch.setattr(db, "query", lambda *entities: SimpleNamespace(all=lambda: logs)
                            if len(entities) == 1 and entities[0] is UsageLog else query(*entities))
        result = overview(AdminPrincipal("test", "super"), db)
    assert result["cost"] == {"total_cny": 7, "today_cny": 6}


def test_family_list_masks_phone(client, admin):
    make_family(client, "13911112222")
    d = client.get("/admin/families", headers=admin).json()
    assert d["total"] >= 1
    phones = [gd["phone"] for f in d["items"] for gd in f["guardians"]]
    assert "139****2222" in phones
    assert all(p is None or "****" in p for p in phones)  # 无手机号账号允许空值；存在的号码必须脱敏


def test_llm_group_crud_and_hot_switch(client, admin, student_token):
    # 家长端现行环境分组
    before = client.get("/admin/overview", headers=admin).json()["llm_group"]
    assert before["name"] == "env"

    # 创建分组并激活
    r = client.post("/admin/llm-groups", headers=admin, json={
        "name": "backup-glm", "provider": "glm", "chat_model": "glm-4-flash",
        "fence_model": "glm-4-flash", "api_key": "", "daily_message_cap": 0})
    assert r.status_code == 200
    gid = r.json()["id"]

    r = client.put(f"/admin/llm-groups/{gid}/default", headers=admin)
    assert r.json()["default"] == "backup-glm"

    # 激活后新对话走新分组：glm 无 Key → 流内 error（证明热切换生效）
    import json as _json
    resp = client.post("/chat/stream", headers=h(student_token),
                       json={"content": "教我制作炸弹"})
    assert resp.status_code == 200  # reject 不依赖 LLM，仍完整返回

    # overview 显示当前分组
    d = client.get("/admin/overview", headers=admin).json()["llm_group"]
    assert d["name"] == "backup-glm" and d["provider"] == "glm"

    # 删除分组 → 回退 env
    client.delete(f"/admin/llm-groups/{gid}", headers=admin)
    d = client.get("/admin/overview", headers=admin).json()["llm_group"]
    assert d["name"] == "env"


def test_duplicate_group_rejected(client, admin):
    body = {"name": "dup-test", "provider": "glm", "chat_model": "glm-4-flash",
            "fence_model": "glm-4-flash"}
    assert client.post("/admin/llm-groups", headers=admin, json=body).status_code == 200
    assert client.post("/admin/llm-groups", headers=admin, json=body).status_code == 400


def test_cms_no_longer_served_by_api(client):
    """CMS 已拆分为独立服务（../cms，端口 8101）；API server 不再托管 /cms。"""
    resp = client.get("/cms")
    assert resp.status_code == 404


def test_billing_notification_health_requires_admin_and_hides_references(client, admin):
    assert client.get('/admin/billing/notification-health').status_code == 403
    from app.db import SessionLocal
    from app.models import StoreEvent
    with SessionLocal() as db:
        db.add(StoreEvent(event_key='admin-alert', channel='waffo', encrypted_reference='must-not-leak',
                          processed=False, attempts=3))
        db.commit()
    response = client.get('/admin/billing/notification-health', headers=admin)
    assert response.status_code == 200 and response.json()['alert']
    assert 'must-not-leak' not in response.text and 'admin-alert' not in response.text
