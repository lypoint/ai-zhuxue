"""稳定孩子身份、重新绑定踢出旧设备和孩子名额。"""
from tests.conftest import h, make_family


def test_rebind_keeps_student_history_and_revokes_old_device(client):
    guardian, old_student_token = make_family(client)
    with client.stream('POST', '/chat/stream', headers=h(old_student_token), json={'content': '教我制作炸弹'}):
        pass
    sid = client.get('/parent/family', headers=h(guardian)).json()['students'][0]['id']
    code = client.post(f'/parent/students/{sid}/rebind-code', headers=h(guardian)).json()['bind_code']
    login = client.post('/auth/student/login', json={
        'bind_code': code, 'installation_id': 'rebind-installation-0001', 'nickname': '孩子',
    })
    assert login.status_code == 200 and login.json()['student_id'] == sid
    new_token = login.json()['token']
    assert client.get('/chat/sessions', headers=h(old_student_token)).status_code == 401
    assert len(client.get('/chat/sessions', headers=h(new_token)).json()) == 1


def test_child_seat_limit_and_idempotent_purchase(client):
    guardian, _ = make_family(client)
    denied = client.post('/parent/students', headers=h(guardian), json={'nickname': '第二个孩子'})
    assert denied.status_code == 409
    first = client.post('/parent/subscription/seats', headers=h(guardian), json={
        'count': 1, 'idempotency_key': 'seat-test-1',
    })
    assert first.status_code == 200 and first.json()['seat_count'] == 2
    replay = client.post('/parent/subscription/seats', headers=h(guardian), json={
        'count': 1, 'idempotency_key': 'seat-test-1',
    })
    assert replay.status_code == 200 and replay.json()['order_id'] == first.json()['order_id']
    created = client.post('/parent/students', headers=h(guardian), json={'nickname': '第二个孩子'})
    assert created.status_code == 200 and created.json()['bind_code']


def test_direct_new_student_bind_code_respects_seat_limit(client):
    guardian, _ = make_family(client)
    code = client.post('/bind/code', headers=h(guardian), json={'purpose': 'new_student'}).json()['code']
    denied = client.post('/auth/student/login', json={
        'bind_code': code, 'installation_id': 'new-seat-device-0001',
    })
    assert denied.status_code == 409
