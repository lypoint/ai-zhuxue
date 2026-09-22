from datetime import datetime

from pydantic import BaseModel, Field


class GuardianRegisterIn(BaseModel):
    phone: str = Field(min_length=11, max_length=11)
    sms_code: str = Field(min_length=4, max_length=6)
    nickname: str = ""
    # 三要素核验（监护人实名信息，权威数据源比对；不采集人脸）
    real_name: str = Field(min_length=2, max_length=30)
    id_number: str = Field(min_length=15, max_length=18)


class TokenOut(BaseModel):
    token: str
    role: str  # guardian | student


class StudentLoginIn(BaseModel):
    bind_code: str
    device_id: str = Field(min_length=8, max_length=64)
    nickname: str = ""


class BindCodeOut(BaseModel):
    code: str
    expires_at: datetime


class ChatIn(BaseModel):
    conversation_id: int | None = None
    content: str = Field(min_length=1, max_length=4000)


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    fence_action: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class ConversationOut(BaseModel):
    id: int
    title: str
    created_at: datetime

    class Config:
        from_attributes = True


class FenceEventOut(BaseModel):
    id: int
    stage: str
    decision: str
    category: str
    confidence: float
    created_at: datetime

    class Config:
        from_attributes = True


class FamilySettingsIn(BaseModel):
    # 部分更新：只改一个策略时，不应把其它家长设置重置为默认值。
    daily_message_cap: int | None = Field(default=None, ge=10, le=1000)
    review_enabled: bool | None = None
    quiet_enabled: bool | None = None        # P1：家长可整体关闭时段限制
    quiet_start: int | None = Field(default=None, ge=0, le=23)
    quiet_end: int | None = Field(default=None, ge=0, le=23)
    daily_minutes_cap: int | None = Field(default=None, ge=0, le=480)  # 0=不限
    notify_fence: bool | None = None  # security 告警不可关闭
