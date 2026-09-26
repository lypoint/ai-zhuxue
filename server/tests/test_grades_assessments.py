"""成绩版本、趋势和评估端到端回归。"""
from tests.conftest import h, make_family


def test_grades_versions_delete_restore_and_assessments(client):
    guardian, student = make_family(client)
    sid = client.get('/parent/family', headers=h(guardian)).json()['students'][0]['id']
    grade = client.post(f'/parent/students/{sid}/grades', headers=h(guardian), json={
        'subject': '数学', 'title': '月考', 'exam_date': '2026-09-20',
        'term': '上学期', 'score': 80.5, 'max_score': 100, 'grade_type': 'exam',
        'note': '函数', 'reason': '录入',
    })
    assert grade.status_code == 200
    gid = grade.json()['id']

    assert len(client.get('/chat/grades', headers=h(student)).json()) == 1
    edited = client.patch(f'/parent/students/{sid}/grades/{gid}', headers=h(guardian), json={
        'score': 88, 'reason': '复核成绩',
    })
    assert edited.status_code == 200 and edited.json()['current_version'] == 2
    history = client.get(f'/parent/students/{sid}/grades/{gid}/history', headers=h(guardian)).json()
    assert [x['version'] for x in history] == [1, 2]

    trend = client.get(f'/parent/students/{sid}/grade-trend', headers=h(guardian)).json()
    assert trend['latest'] == 88.0 and trend['direction'] == 'insufficient'

    assert client.delete(f'/parent/students/{sid}/grades/{gid}', headers=h(guardian)).status_code == 200
    assert client.get(f'/parent/students/{sid}/grades', headers=h(guardian)).json() == []
    assert len(client.get(f'/parent/students/{sid}/grades?include_deleted=true', headers=h(guardian)).json()) == 1
    assert client.post(f'/parent/students/{sid}/grades/{gid}/restore', headers=h(guardian)).status_code == 200
    assert len(client.get(f'/parent/students/{sid}/grades', headers=h(guardian)).json()) == 1

    # The evidence contract carries both the message and conversation ids.
    with client.stream('POST', '/chat/stream', headers=h(student), json={'content': '我最近考试压力很大'}):
        pass
    academic = client.post(f'/parent/students/{sid}/academic-assessments', headers=h(guardian), json={})
    assert academic.status_code == 200 and 'disclaimer' in academic.json()
    wellbeing = client.post(f'/parent/students/{sid}/wellbeing-assessments', headers=h(guardian), json={})
    assert wellbeing.status_code == 200 and 'signals' in wellbeing.json()
    signal = wellbeing.json()['signals'][0]
    assert signal['evidence'] and signal['evidence_conversation_ids']
    assessment_id = wellbeing.json()['assessment_id']
    assert client.post(f'/parent/wellbeing-assessments/{assessment_id}/ack', headers=h(guardian), json={'status': 'acknowledged'}).json()['ack_status'] == 'acknowledged'


def test_assessment_input_version_changes_when_an_older_grade_is_edited(client):
    guardian, student = make_family(client)
    sid = client.get('/parent/family', headers=h(guardian)).json()['students'][0]['id']
    first = client.post(f'/parent/students/{sid}/grades', headers=h(guardian), json={
        'subject': '数学', 'exam_date': '2026-09-01', 'score': 70, 'max_score': 100,
    }).json()
    client.post(f'/parent/students/{sid}/grades', headers=h(guardian), json={
        'subject': '语文', 'exam_date': '2026-09-02', 'score': 80, 'max_score': 100,
    })
    first_assessment = client.post(f'/parent/students/{sid}/academic-assessments', headers=h(guardian), json={}).json()
    client.patch(f"/parent/students/{sid}/grades/{first['id']}", headers=h(guardian), json={'score': 75})
    second_assessment = client.post(f'/parent/students/{sid}/academic-assessments', headers=h(guardian), json={}).json()
    assert second_assessment['assessment_id'] != first_assessment['assessment_id']
