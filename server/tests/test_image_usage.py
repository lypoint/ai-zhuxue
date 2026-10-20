"""Image statistics isolate image calls and use business-day UTC boundaries."""
from datetime import datetime, timedelta

import pytest

from app.api import image_admin
from app.db import SessionLocal
from app.models import UsageLog
from tests.conftest import make_admin


def test_image_usage_aggregation_and_day_boundaries(client, monkeypatch):
    monkeypatch.setattr(image_admin, 'local_now', lambda: datetime(2026, 10, 20, 12))
    start, end = image_admin.utc_bounds('2026-10-20')
    model = 'usage-stat-test'
    with SessionLocal.begin() as db:
        for purpose, provider, when, tin, tout, cost in [
            ('vision', 'image', start, 10, 2, .1),
            ('vision', 'image', end - timedelta(microseconds=1), 20, 3, .2),
            ('vision', 'image', start - timedelta(seconds=1), 30, 4, .3),
            ('image_generate', 'image', start, 0, 0, .4),
            ('image_plan', 'image', start, 5, 1, 0),
            ('image_review', 'image', start, 6, 2, 0),
            ('vision', 'image', end, 40, 5, .5),
            ('chat', 'image', start, 999, 999, 99),
            ('vision', 'other', start, 999, 999, 99),
        ]:
            db.add(UsageLog(model=model, purpose=purpose, provider=provider, created_at=when,
                            tokens_in=tin, tokens_out=tout, cost=cost))
    try:
        headers = make_admin(client)
        def rows(period):
            response = client.get('/admin/image-usage', params={'period': period}, headers=headers)
            assert response.status_code == 200
            return {r['purpose']: r for r in response.json()['items'] if r['model'] == model}
        today = rows('today')
        assert set(today) == {'vision', 'image_generate', 'image_plan', 'image_review'}
        assert today['vision']['calls'] == 2
        assert today['vision']['tokens_in'] == 30
        assert today['vision']['tokens_out'] == 5
        assert today['vision']['cost'] == pytest.approx(.3)
        assert today['image_generate']['cost'] == pytest.approx(.4)
        assert rows('all')['vision']['calls'] == 4
        assert client.get('/admin/image-usage?period=invalid', headers=headers).status_code == 422
    finally:
        with SessionLocal.begin() as db:
            db.query(UsageLog).filter_by(model=model).delete()


def test_image_usage_access_and_empty_result(client):
    assert client.get('/admin/image-usage').status_code == 403
    assert client.get('/admin/image-usage', headers=make_admin(client, 'support')).status_code == 403
    for role in ['super', 'admin']:
        response = client.get('/admin/image-usage', headers=make_admin(client, role))
        assert response.status_code == 200
        assert isinstance(response.json()['items'], list)
