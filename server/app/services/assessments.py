"""Deterministic first-pass learning/wellbeing summaries.

These are explainable fallbacks; a later model can replace the scorer while
keeping the same evidence and disclaimer contract.
"""
import json
import hashlib
from datetime import datetime, timedelta

from sqlalchemy.orm import Session
from sqlalchemy import func

from ..models import (AcademicAssessment, AssessmentAudit, Conversation, FenceEvent,
                      Message, Student, StudentGrade, WellbeingAssessment)

SUBJECT_HINTS = {
    "数学": ("数学", "方程", "函数", "几何", "三角", "计算"),
    "语文": ("语文", "作文", "阅读", "古诗", "成语"),
    "英语": ("英语", "单词", "语法", "翻译"),
    "科学": ("物理", "化学", "生物", "光合", "细胞", "实验"),
}
WELLBEING_HINTS = {
    "school_stress": ("考试压力", "成绩压力", "作业压力", "学不完", "焦虑", "害怕考试"),
    "peer_support": ("被欺负", "霸凌", "没人和我玩", "孤单", "同学欺负"),
    "low_mood": ("难过", "不想上学", "没意思", "很累", "睡不着", "不开心"),
    "self_harm": ("自杀", "自残", "割腕", "轻生", "不想活"),
}


def _rows(db: Session, student_id: int, start: str, end: str):
    start_dt = datetime.fromisoformat(start)
    end_dt = datetime.fromisoformat(end) + timedelta(days=1)
    return (db.query(Message).join(Conversation, Message.conversation_id == Conversation.id)
            .filter(Conversation.student_id == student_id,
                    Message.created_at >= start_dt, Message.created_at < end_dt)
            .order_by(Message.id).all())


def input_version(db: Session, student_id: int, start: str, end: str) -> str:
    rows = _rows(db, student_id, start, end)
    # Include deleted grades in the version: a logical delete/restore changes
    # the assessment input even though deleted rows are omitted from results.
    grades = (db.query(StudentGrade).filter_by(student_id=student_id)
              .order_by(StudentGrade.id.desc()).all())
    fences = (db.query(FenceEvent.id).filter(FenceEvent.student_id == student_id,
                                              FenceEvent.created_at >= datetime.fromisoformat(start),
                                              FenceEvent.created_at < datetime.fromisoformat(end) + timedelta(days=1))
              .order_by(FenceEvent.id.desc()).first())
    grade_facts = ";".join(
        f"{g.id}:{g.current_version}:{1 if g.deleted_at else 0}"
        for g in sorted(grades, key=lambda item: item.id)
    ) or "0"
    grade_version = hashlib.sha256(grade_facts.encode()).hexdigest()[:16]
    return f"m{rows[-1].id if rows else 0}-g{grade_version}-f{fences[0] if fences else 0}"


def generation_count(db: Session, family_id: int, assessment_type: str,
                     since: datetime) -> int:
    """Count generated assessments for the whole family, across guardians."""
    model = AcademicAssessment if assessment_type == "academic" else WellbeingAssessment
    return int(db.query(AssessmentAudit).join(
        model, AssessmentAudit.assessment_id == model.id
    ).join(Student, Student.id == model.student_id).filter(
        Student.family_id == family_id,
        AssessmentAudit.assessment_type == assessment_type,
        AssessmentAudit.action == "generate",
        AssessmentAudit.created_at >= since,
    ).count())


def teacher_snapshots(db: Session, student_id: int,
                      conversation_ids: set[int] | None = None) -> list[dict]:
    result, seen = [], set()
    query = db.query(Conversation).filter(Conversation.student_id == student_id)
    if conversation_ids is not None:
        if not conversation_ids:
            return []
        query = query.filter(Conversation.id.in_(conversation_ids))
    for conv in query.all():
        key = (conv.teacher_group_id, conv.teacher_name_snapshot, conv.teacher_avatar_snapshot)
        if key in seen:
            continue
        seen.add(key)
        result.append({"teacher_id": conv.teacher_group_id,
                       "teacher_name": conv.teacher_name_snapshot,
                       "teacher_avatar_url": conv.teacher_avatar_snapshot})
    return result


def academic(db: Session, student_id: int, start: str, end: str) -> dict:
    all_rows = _rows(db, student_id, start, end)
    conversation_ids = {m.conversation_id for m in all_rows}
    rows = [m for m in all_rows if m.role == "user"]
    subjects = []
    for subject, hints in SUBJECT_HINTS.items():
        matched = [m for m in rows if any(h in (m.content or "") for h in hints)]
        if matched:
            subjects.append({
                "subject": subject,
                "question_count": len(matched),
                "evidence_message_ids": [m.id for m in matched[:10]],
                "evidence_conversation_ids": sorted({m.conversation_id for m in matched[:10]}),
            })
    grades = db.query(StudentGrade).filter_by(student_id=student_id, deleted_at=None).all()
    mastered = [g.subject for g in grades if g.max_score and g.score / g.max_score >= .8]
    needs = [g.subject for g in grades if g.max_score and g.score / g.max_score < .6]
    fences = (db.query(FenceEvent.decision, func.count(FenceEvent.id))
              .filter(FenceEvent.student_id == student_id,
                      FenceEvent.created_at >= datetime.fromisoformat(start),
                      FenceEvent.created_at < datetime.fromisoformat(end) + timedelta(days=1))
              .group_by(FenceEvent.decision).all())
    return {"subjects": subjects, "mastery_signals": mastered, "needs_practice": needs,
            "question_count": len(rows), "assistant_message_count": sum(1 for m in all_rows if m.role == "assistant"),
            "fence_summary": {decision: count for decision, count in fences},
            "teacher_snapshots": teacher_snapshots(db, student_id, conversation_ids),
            "recommendations": [f"继续练习{subject}" for subject in sorted(set(needs))] or ["保持每周复习并检查错题"],
            "disclaimer": "这是基于对话和成绩的 AI 辅助估计，不是学校成绩或诊断。"}


def wellbeing(db: Session, student_id: int, start: str, end: str) -> dict:
    rows = [m for m in _rows(db, student_id, start, end) if m.role == "user"]
    conversation_ids = {m.conversation_id for m in rows}
    signals = []
    for kind, hints in WELLBEING_HINTS.items():
        hits = [m for m in rows if any(h in (m.content or "") for h in hints)]
        if hits:
            level = "urgent" if kind == "self_harm" else ("observe" if len(hits) < 3 else "attention")
            signals.append({"type": kind, "level": level,
                            "confidence": min(.95, .45 + .12 * len(hits)),
                            "evidence_message_ids": [m.id for m in hits[:10]],
                            "evidence_conversation_ids": sorted({m.conversation_id for m in hits[:10]}),
                            "evidence": [{"message_id": m.id,
                                          "conversation_id": m.conversation_id,
                                          "created_at": m.created_at.isoformat() if m.created_at else None,
                                          "excerpt": (m.content or "")[:160]}
                                         for m in hits[:10]],
                            "summary": f"发现 {len(hits)} 条相关表达"})
    return {"signals": signals,
            "teacher_snapshots": teacher_snapshots(db, student_id, conversation_ids),
            "recommendations": ["主动倾听并与孩子沟通", "必要时联系老师或专业机构"],
            "disclaimer": "这不是医疗诊断，请结合实际沟通判断；紧急风险请立即联系当地专业支持。"}


def dumps(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False)
