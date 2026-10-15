"""Teacher availability follows the distribution channel, independent of billing."""
from typing import Literal

from fastapi import Header

from ..models import LLMGroup

Channel = Literal["wechat", "appstore", "googleplay"]
TeacherChannel = Literal["all", "wechat", "appstore", "googleplay"]


def current_channel(x_app_channel: Channel = Header(default="wechat")) -> str:
    return x_app_channel


def channel_teachers(db, channel: str):
    return db.query(LLMGroup).filter(
        LLMGroup.teacher_enabled.is_(True),
        LLMGroup.teacher_channel.in_(("all", channel)),
    ).order_by(LLMGroup.teacher_sort_order, LLMGroup.id)
