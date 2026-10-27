from tests.conftest import h, make_family


def test_final_fence_events_hide_internal_steps_and_keep_latest_decisions(client):
    from app.db import SessionLocal
    from app.models import Conversation, FenceEvent, Message
    from app.security import parse_token

    guardian, student = make_family(client)
    other_guardian, _ = make_family(client)
    with SessionLocal.begin() as db:
        sid = int(parse_token(student)["sub"])
        conv = Conversation(student_id=sid, title="Final decisions")
        db.add(conv)
        db.flush()
        cid = conv.id
        messages = [Message(conversation_id=cid, role="user", content="Question") for _ in range(5)]
        db.add_all(messages)
        db.flush()
        steps = [
            (0, "classifier", "pending", "entertainment"),
            (0, "context_check", "allow", "entertainment"),
            (0, "second_pass", "allow", "other"),
            (0, "policy", "rewrite", "other"),
            (1, "policy", "reject", "sensitive"),
            (1, "policy", "rewrite", "sensitive"),
            (2, "parent_keywords", "reject", "other"),
            (3, "policy", "allow", "study"),
            (3, "output_check", "reject", "sensitive"),
            (4, "classifier", "pending", "study"),
            (4, "whitelist", "allow", "study"),
            (4, "policy", "pending", "study"),
            (4, "policy", "unknown", "study"),
            (None, "policy", "allow", "study"),
            (None, "parent_keywords", "reject", "other"),
        ]
        for index, stage, decision, category in steps:
            db.add(FenceEvent(student_id=sid, conversation_id=cid,
                              message_id=messages[index].id if index is not None else None,
                              stage=stage, decision=decision, category=category, confidence=1))
    path = f"/parent/conversations/{cid}/fence-events"
    raw = client.get(path, headers=h(guardian)).json()
    response = client.get(path + "?final_only=true", headers=h(guardian))
    assert response.status_code == 200, response.text
    final = response.json()
    assert [(event["stage"], event["decision"]) for event in final] == [
        ("policy", "rewrite"), ("policy", "rewrite"), ("parent_keywords", "reject"),
        ("output_check", "reject"), ("policy", "allow"), ("parent_keywords", "reject")]
    assert [event["id"] for event in final] == sorted(event["id"] for event in final)
    assert len(raw) == len(steps)
    assert client.get(path, headers=h(guardian)).json() == raw
    assert client.get(path + "?final_only=true", headers=h(other_guardian)).status_code == 404
    assert client.get(path + "?final_only=true", headers=h("invalid-token")).status_code == 401


def test_final_fence_events_can_be_empty_while_audit_records_exist(client):
    from app.db import SessionLocal
    from app.models import Conversation, FenceEvent
    from app.security import parse_token

    guardian, student = make_family(client)
    sid = int(parse_token(student)["sub"])
    with SessionLocal.begin() as db:
        conv = Conversation(student_id=sid, title="Classification only")
        db.add(conv)
        db.flush()
        cid = conv.id
        db.add(FenceEvent(student_id=sid, conversation_id=cid, stage="classifier",
                          decision="pending", category="study", confidence=1))
    path = f"/parent/conversations/{cid}/fence-events"
    assert client.get(path + "?final_only=true", headers=h(guardian)).json() == []
    assert len(client.get(path, headers=h(guardian)).json()) == 1
