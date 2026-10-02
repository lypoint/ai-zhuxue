from app.db import SessionLocal
from app.models import Conversation, Message, Student
from app.security import parse_token
from tests.conftest import h, make_admin, make_family


def test_student_report_cms_reply_and_ownership(client):
    _, student_token = make_family(client)
    _, other_token = make_family(client)
    admin = make_admin(client)
    with SessionLocal.begin() as db:
        student = db.get(Student, int(parse_token(student_token)["sub"]))
        conv = Conversation(student_id=student.id, title="举报测试")
        db.add(conv)
        db.flush()
        message = Message(conversation_id=conv.id, role="assistant", content="测试回复")
        db.add(message)
        db.flush()
        message_id = message.id

    path = "/chat/reports"
    assert client.post(path, headers=h(other_token), json={"message_id": message_id,
        "reason": "不准确"}).status_code == 404
    submitted = client.post(path, headers=h(student_token), json={"message_id": message_id,
        "reason": "内容不准确"})
    assert submitted.status_code == 200, submitted.text
    report_id = submitted.json()["id"]
    assert client.post(path, headers=h(student_token), json={"message_id": message_id,
        "reason": "内容不准确"}).json()["already"] is True
    assert client.get(path, headers=h(other_token)).json() == []

    listing = client.get("/admin/fence-feedback?kind=message_report", headers=admin).json()
    assert any(item["id"] == report_id and item["note"] == "内容不准确"
               for item in listing["items"])
    reply_url = f"/admin/fence-feedback/{report_id}"
    assert client.patch(reply_url, headers=admin,
        json={"status": "reviewed"}).status_code == 422
    assert client.patch(reply_url, headers=admin,
        json={"status": "reviewed", "reply": "已核实，感谢反馈"}).status_code == 200
    assert client.patch(reply_url, headers=admin,
        json={"status": "reviewed", "reply": " "}).status_code == 422
    reports = client.get(path, headers=h(student_token)).json()
    assert reports[0]["reply"] == "已核实，感谢反馈"
    assert reports[0]["status"] == "reviewed"
