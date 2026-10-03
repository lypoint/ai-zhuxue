"""Honest feedback, daily participation rewards, and family reward agreements."""
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import update
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (Student, Guardian, Message, Conversation, LearningFeedback,
                      LearningFeedbackEvent, LearningDayReward, RewardAgreement, RewardRedemption, utcnow)
from ..local_time import local_now
from ..config import settings
from .deps import current_student, current_guardian
from .parent import _own_student

router = APIRouter(tags=["learning"])
LABELS = {"understood": "懂了", "not_understood": "不懂", "continue": "继续讲解"}


class FeedbackIn(BaseModel):
    action: Literal["understood", "not_understood", "continue"]


class AgreementIn(BaseModel):
    reward: str = Field(min_length=1, max_length=200)
    stars: int = Field(ge=1, le=100000)
    fulfillment: str = Field(min_length=1, max_length=100)
    request_id: str = Field(min_length=1, max_length=64)


class RedemptionIn(BaseModel):
    agreement_id: int = Field(ge=1)
    request_id: str = Field(min_length=1, max_length=64)


def lock_student(db, student_id):
    # Serialize feedback grants and balance deductions on both SQLite and PostgreSQL.
    db.execute(update(Student).where(Student.id == student_id).values(nickname=Student.nickname))


def day_of(timestamp):
    return (timestamp + timedelta(hours=settings.tz_offset_hours)).date().isoformat()


def summary(db, student_id):
    days = {}
    events = db.query(LearningFeedbackEvent).filter_by(student_id=student_id).order_by(LearningFeedbackEvent.id).all()
    for row in events:
        counts = days.setdefault(day_of(row.created_at), dict.fromkeys(LABELS, 0))
        counts[row.action] += 1
    rewards = {r.day for r in db.query(LearningDayReward).filter_by(student_id=student_id).all()}
    daily = []
    for day in sorted(set(days) | rewards, reverse=True):
        counts = days.get(day, dict.fromkeys(LABELS, 0))
        total = sum(counts.values())
        daily.append(dict(date=day, counts=counts, total=total,
                          ratios={k: v / total if total else 0 for k, v in counts.items()}, stars=int(day in rewards)))
    redemptions = db.query(RewardRedemption).filter_by(student_id=student_id).order_by(RewardRedemption.id.desc()).all()
    agreements = db.query(RewardAgreement).filter_by(student_id=student_id).order_by(RewardAgreement.id.desc()).all()
    spent = sum(row.stars for row in redemptions)
    return dict(days=daily, earned=len(rewards), spent=spent, balance=len(rewards)-spent,
                rule="每天完成一次学习并提交任一种反馈，获得1颗参与小行星，每天最多1颗；更新旧回答反馈不会重复发奖",
                agreements=[dict(id=r.id, reward=r.reward, stars=r.stars, fulfillment=r.fulfillment,
                                 accepted=r.accepted_at is not None) for r in agreements],
                history=[dict(message_id=r.message_id, action=r.action, label=LABELS[r.action],
                              created_at=r.created_at.isoformat()) for r in reversed(events)],
                redemptions=[dict(id=r.id, reward=r.reward, stars=r.stars, fulfillment=r.fulfillment,
                                  fulfilled=r.fulfilled_at is not None, created_at=r.created_at.isoformat()) for r in redemptions])


@router.post("/chat/messages/{message_id}/learning-feedback")
def feedback(message_id: int, body: FeedbackIn, student: Student = Depends(current_student), db: Session = Depends(get_db)):
    lock_student(db, student.id)
    message = db.get(Message, message_id)
    conv = db.get(Conversation, message.conversation_id) if message else None
    if not conv or conv.student_id != student.id or conv.student_deleted or message.role != "assistant":
        raise HTTPException(404, "回答不存在")
    if message.fence_action not in (None, "allow", "rewrite") or not message.content.strip():
        raise HTTPException(409, "此消息不能提交学习反馈")
    row = db.query(LearningFeedback).filter_by(message_id=message_id).first()
    changed = row is None or row.action != body.action
    if row is None:
        row = LearningFeedback(student_id=student.id, message_id=message_id, action=body.action)
        db.add(row)
    if changed:
        row.action = body.action
        db.add(LearningFeedbackEvent(student_id=student.id, message_id=message_id, action=body.action))
    today = local_now().date().isoformat()
    # A completed answer to the child's question today qualifies; old cards cannot be farmed daily.
    question = db.query(Message.id).filter(Message.conversation_id == conv.id,
        Message.role == "user", Message.id < message_id).first()
    awarded = False
    if question and day_of(message.created_at) == today and not db.query(LearningDayReward.id).filter_by(student_id=student.id, day=today).first():
        db.add(LearningDayReward(student_id=student.id, day=today))
        awarded = True
    db.commit()
    return dict(action=row.action, changed=changed, awarded=awarded, **summary(db, student.id))


@router.get("/chat/learning")
def student_summary(student: Student = Depends(current_student), db: Session = Depends(get_db)):
    return summary(db, student.id)


@router.get("/chat/learning-feedback")
def student_feedback(student: Student = Depends(current_student), db: Session = Depends(get_db)):
    return {str(r.message_id): r.action for r in db.query(LearningFeedback).filter_by(student_id=student.id).all()}


@router.get("/parent/students/{student_id}/learning")
def parent_summary(student_id: int, guardian: Guardian = Depends(current_guardian), db: Session = Depends(get_db)):
    _own_student(guardian, student_id, db)
    return summary(db, student_id)


@router.post("/parent/students/{student_id}/reward-agreements")
def propose(student_id: int, body: AgreementIn, guardian: Guardian = Depends(current_guardian), db: Session = Depends(get_db)):
    _own_student(guardian, student_id, db)
    lock_student(db, student_id)
    reward, fulfillment = body.reward.strip(), body.fulfillment.strip()
    if not reward or not fulfillment:
        raise HTTPException(422, "请填写奖励内容和兑现时间")
    existing = db.query(RewardAgreement).filter_by(student_id=student_id, request_id=body.request_id).first()
    if existing:
        if (existing.reward, existing.stars, existing.fulfillment) != (reward, body.stars, fulfillment):
            raise HTTPException(409, "请求编号已使用")
    else:
        db.add(RewardAgreement(student_id=student_id, guardian_id=guardian.id, reward=reward,
                               stars=body.stars, fulfillment=fulfillment, request_id=body.request_id))
    db.commit()
    return summary(db, student_id)


@router.post("/chat/reward-agreements/{agreement_id}/accept")
def accept(agreement_id: int, student: Student = Depends(current_student), db: Session = Depends(get_db)):
    lock_student(db, student.id)
    row = db.get(RewardAgreement, agreement_id)
    if not row or row.student_id != student.id:
        raise HTTPException(404, "奖励约定不存在")
    if row.accepted_at is None:
        row.accepted_at = utcnow()
    db.commit()
    return summary(db, student.id)


def redeem_agreement(db, student_id, body):
    lock_student(db, student_id)
    agreement = db.get(RewardAgreement, body.agreement_id)
    if not agreement or agreement.student_id != student_id:
        raise HTTPException(404, "奖励约定不存在")
    if agreement.accepted_at is None:
        raise HTTPException(409, "请先让孩子确认奖励约定")
    existing = db.query(RewardRedemption).filter_by(student_id=student_id, request_id=body.request_id).first()
    if existing:
        if existing.agreement_id != agreement.id:
            raise HTTPException(409, "兑换请求编号已使用")
        return summary(db, student_id)
    if summary(db, student_id)["balance"] < agreement.stars:
        raise HTTPException(409, "小行星余额不足")
    db.add(RewardRedemption(student_id=student_id, guardian_id=agreement.guardian_id,
        agreement_id=agreement.id, reward=agreement.reward, stars=agreement.stars,
        fulfillment=agreement.fulfillment, request_id=body.request_id))
    db.commit()
    return summary(db, student_id)


@router.post("/parent/students/{student_id}/redemptions")
def redeem(student_id: int, body: RedemptionIn, guardian: Guardian = Depends(current_guardian), db: Session = Depends(get_db)):
    _own_student(guardian, student_id, db)
    return redeem_agreement(db, student_id, body)


@router.post("/chat/redemptions")
def student_redeem(body: RedemptionIn, student: Student = Depends(current_student), db: Session = Depends(get_db)):
    return redeem_agreement(db, student.id, body)


@router.post("/parent/students/{student_id}/redemptions/{redemption_id}/fulfill")
def fulfill(student_id: int, redemption_id: int, guardian: Guardian = Depends(current_guardian), db: Session = Depends(get_db)):
    _own_student(guardian, student_id, db)
    lock_student(db, student_id)
    row = db.get(RewardRedemption, redemption_id)
    if not row or row.student_id != student_id:
        raise HTTPException(404, "兑换记录不存在")
    if row.fulfilled_at is None:
        row.fulfilled_at = utcnow()
    db.commit()
    return summary(db, student_id)
