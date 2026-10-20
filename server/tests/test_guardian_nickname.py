import pytest

from tests.conftest import h, make_family


def test_guardian_rename_persists_and_only_changes_self(client):
    guardian, student = make_family(client)
    other, _ = make_family(client)
    before = client.get('/parent/family', headers=h(guardian)).json()
    result = client.put('/parent/guardian/nickname', headers=h(guardian),
                        json={'nickname': '  小明妈妈  '})
    assert result.status_code == 200
    assert result.json() == {'ok': True, 'nickname': '小明妈妈'}
    family = client.get('/parent/family', headers=h(guardian)).json()
    assert family['guardian']['nickname'] == '小明妈妈'
    assert family['students'] == before['students']
    assert client.get('/parent/family', headers=h(other)).json()['guardian']['nickname'] == '测试'
    relogin = client.post('/auth/guardian/register', json={
        'phone': family['guardian']['phone'], 'sms_code': '123456', 'nickname': '家长',
    }).json()['token']
    assert client.get('/parent/family', headers=h(relogin)).json()['guardian']['nickname'] == '小明妈妈'
    assert client.put('/parent/guardian/nickname', headers=h(student),
                      json={'nickname': '非法修改'}).status_code == 403


@pytest.mark.parametrize('nickname', ['', '   ', 'a' * 51, None, 123, [], {}])
def test_invalid_guardian_name_does_not_change_profile(client, nickname):
    guardian, _ = make_family(client)
    result = client.put('/parent/guardian/nickname', headers=h(guardian),
                        json={'nickname': nickname})
    assert result.status_code == 422
    assert client.get('/parent/family', headers=h(guardian)).json()['guardian']['nickname'] == '测试'


def test_guardian_name_max_length(client):
    guardian, _ = make_family(client)
    name = '家' * 50
    assert client.put('/parent/guardian/nickname', headers=h(guardian),
                      json={'nickname': name}).json()['nickname'] == name
