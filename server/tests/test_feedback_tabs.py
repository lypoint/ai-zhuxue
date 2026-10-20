"""Handled queues include reviewed and dismissed feedback without mixing kinds."""
import pytest

from app.db import SessionLocal
from app.models import Conversation, FenceFeedback
from app.security import parse_token
from tests.conftest import make_admin, make_family


@pytest.mark.parametrize('kind', ['false_positive', 'message_report'])
def test_handled_feedback_filter_and_pagination(client, kind):
    _, token = make_family(client)
    sid = int(parse_token(token)['sub'])
    with SessionLocal.begin() as db:
        conv = Conversation(student_id=sid, title='feedback tabs')
        db.add(conv)
        db.flush()
        cid = conv.id
        rows = [FenceFeedback(student_id=sid, conversation_id=cid, reporter_id=sid,
                              kind=kind, status=status) for status in ['open', 'reviewed', 'dismissed']]
        db.add_all(rows)
        db.flush()
        open_id, reviewed_id, dismissed_id = [row.id for row in rows]
    try:
        headers = make_admin(client)
        url = f'/admin/fence-feedback?kind={kind}'
        handled = client.get(url+'&status=handled&size=1', headers=headers).json()
        assert handled['items'][0]['id'] == dismissed_id
        assert handled['total'] >= 2
        page2 = client.get(url+'&status=handled&size=1&page=2', headers=headers).json()
        assert page2['items'][0]['id'] == reviewed_id
        assert client.get(url+'&status=open&size=1', headers=headers).json()['items'][0]['id'] == open_id
        assert client.get(url+'&status=reviewed&size=1', headers=headers).json()['items'][0]['id'] == reviewed_id
        assert client.get(url+'&status=dismissed&size=1', headers=headers).json()['items'][0]['id'] == dismissed_id
        assert client.get(url+'&status=bad', headers=headers).status_code == 422
    finally:
        with SessionLocal.begin() as db:
            db.query(FenceFeedback).filter_by(conversation_id=cid).delete()
