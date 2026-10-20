"""Teacher availability follows the distribution channel, independent of billing."""
from typing import Literal

from fastapi import Header

from ..models import ChannelTeacherDefault, LLMGroup

Channel = Literal["wechat", "appstore", "googleplay"]
TeacherChannel = Literal["all", "wechat", "appstore", "googleplay"]


def current_channel(x_app_channel: Channel = Header(default="wechat")) -> str:
    return x_app_channel


def channel_teachers(db, channel: str):
    return db.query(LLMGroup).filter(
        LLMGroup.teacher_enabled.is_(True),
        LLMGroup.teacher_channel.in_(("all", channel)),
    ).order_by(LLMGroup.teacher_sort_order, LLMGroup.id)


def default_teacher(db, channel: str):
    configured = db.get(ChannelTeacherDefault, channel)
    if configured is not None:
        return channel_teachers(db, channel).filter_by(id=configured.teacher_group_id).first()
    # Preserve pre-migration behavior for callers bootstrapping without Alembic.
    return channel_teachers(db, channel).filter_by(is_active=True).first()


def clear_unavailable_defaults(db, group):
    rows = db.query(ChannelTeacherDefault).filter_by(teacher_group_id=group.id).all()
    cleared = []
    for row in rows:
        if not group.teacher_enabled or group.teacher_channel not in ("all", row.channel):
            row.teacher_group_id = None
            cleared.append(row.channel)
    return cleared
