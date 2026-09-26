"""数据模型。命名与评审材料口径一致：Family（家庭）/Guardian（监护人）/Student（学生）。"""
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow():
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Family(TimestampMixin, Base):
    __tablename__ = "families"
    id: Mapped[int] = mapped_column(primary_key=True)
    # 家庭标签（如 beta/vip/free-trial）：绑定同名 llm_groups.tag 的分组，决定该家庭用哪个 provider/model
    tag: Mapped[str | None] = mapped_column(String(50), nullable=True)

    guardians: Mapped[list["Guardian"]] = relationship(back_populates="family")
    students: Mapped[list["Student"]] = relationship(back_populates="family")
    settings: Mapped["FamilySettings"] = relationship(back_populates="family", uselist=False)


class Guardian(TimestampMixin, Base):
    __tablename__ = "guardians"
    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"))
    phone: Mapped[str] = mapped_column(String(20), unique=True)
    nickname: Mapped[str] = mapped_column(String(50), default="")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    token_version: Mapped[int] = mapped_column(Integer, default=1)  # 登出即 +1，旧 token 全部失效

    family: Mapped["Family"] = relationship(back_populates="guardians")


class Student(TimestampMixin, Base):
    __tablename__ = "students"
    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"))
    nickname: Mapped[str] = mapped_column(String(50), default="")
    grade_band: Mapped[str] = mapped_column(String(10), default="8-12")  # 8-12 | 12-16 | 16-18
    device_id: Mapped[str] = mapped_column(String(64), unique=True)      # 学生端设备标识
    installation_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    token_version: Mapped[int] = mapped_column(Integer, default=1)  # 登出即 +1

    family: Mapped["Family"] = relationship(back_populates="students")
    conversations: Mapped[list["Conversation"]] = relationship(
        back_populates="student", foreign_keys="Conversation.student_id")

    @property
    def seat_status(self) -> str:
        return "active" if self.active else "released"


class BindCode(TimestampMixin, Base):
    """学生端扫码绑定家长端的一次性码。"""
    __tablename__ = "bind_codes"
    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"))
    code: Mapped[str] = mapped_column(String(12), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_by_student_id: Mapped[int | None] = mapped_column(ForeignKey("students.id"), nullable=True)
    target_student_id: Mapped[int | None] = mapped_column(ForeignKey("students.id"), nullable=True)
    purpose: Mapped[str] = mapped_column(String(20), default="new_student")  # new_student|rebind
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class StudentDevice(TimestampMixin, Base):
    """孩子业务身份下的设备会话；重新绑定时只保留最新设备。"""
    __tablename__ = "student_devices"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)
    installation_id: Mapped[str] = mapped_column(String(64), unique=True)
    device_name: Mapped[str] = mapped_column(String(100), default="")
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("uq_student_current_device", "student_id", unique=True,
              sqlite_where=text("is_current = 1"),
              postgresql_where=text("is_current = true")),
    )

    student: Mapped["Student"] = relationship()


class FamilySettings(TimestampMixin, Base):
    """家长端管控设置（未成年人模式建设指南：时长管控、家长豁免）。"""
    __tablename__ = "family_settings"
    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"), unique=True)
    daily_message_cap: Mapped[int] = mapped_column(Integer, default=200)  # 覆盖全局配置
    review_enabled: Mapped[bool] = mapped_column(Boolean, default=True)   # 家长审查开关（默认开）
    # 家长自定义禁用时段（P1：覆盖全局 22-6）；quiet_enabled=False 表示家长关闭时段限制
    quiet_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    quiet_start: Mapped[int] = mapped_column(Integer, default=22)
    quiet_end: Mapped[int] = mapped_column(Integer, default=6)
    daily_minutes_cap: Mapped[int] = mapped_column(Integer, default=60)  # 每日使用时长上限（分钟），0=不限
    notify_fence: Mapped[bool] = mapped_column(Boolean, default=True)  # P2：学习引导通知开关（security 告警不可关）

    family: Mapped["Family"] = relationship(back_populates="settings")


class Conversation(TimestampMixin, Base):
    __tablename__ = "conversations"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"))
    title: Mapped[str] = mapped_column(String(100), default="新对话")
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)  # 学生端置顶
    student_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    student_deleted_by: Mapped[int | None] = mapped_column(ForeignKey("students.id"), nullable=True)
    deleted_reason: Mapped[str] = mapped_column(String(200), default="")
    teacher_group_id: Mapped[int | None] = mapped_column(ForeignKey("llm_groups.id"), nullable=True)
    teacher_name_snapshot: Mapped[str] = mapped_column(String(50), default="AI 老师")
    teacher_avatar_snapshot: Mapped[str] = mapped_column(String(500), default="")

    student: Mapped["Student"] = relationship(
        back_populates="conversations", foreign_keys=[student_id])
    messages: Mapped[list["Message"]] = relationship(back_populates="conversation")

    @property
    def student_deleted(self) -> bool:
        return self.student_deleted_at is not None

    @property
    def teacher_id(self) -> int | None:
        return self.teacher_group_id

    @property
    def teacher_name(self) -> str:
        return self.teacher_name_snapshot

    @property
    def teacher_avatar_url(self) -> str:
        return self.teacher_avatar_snapshot


class Message(TimestampMixin, Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id"), index=True)  # 会话消息查询高频
    role: Mapped[str] = mapped_column(String(10))                  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    fence_action: Mapped[str | None] = mapped_column(String(10), nullable=True)  # allow|rewrite|reject
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")
    fence_events: Mapped[list["FenceEvent"]] = relationship(back_populates="message")


class FenceEvent(TimestampMixin, Base):
    """围栏判定流水：审计与误拦截分析的基础数据。"""
    __tablename__ = "fence_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"))
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"))
    message_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id"), nullable=True)
    stage: Mapped[str] = mapped_column(String(20))     # whitelist | classifier | second_pass | policy
    decision: Mapped[str] = mapped_column(String(10))  # allow | rewrite | reject
    category: Mapped[str] = mapped_column(String(20))  # study | entertainment | sensitive | other | unknown
    confidence: Mapped[float] = mapped_column(default=1.0)
    detail: Mapped[str] = mapped_column(Text, default="")
    intent: Mapped[str] = mapped_column(String(30), default="")
    safety_education: Mapped[bool] = mapped_column(Boolean, default=False)

    message: Mapped["Message"] = relationship(back_populates="fence_events")


class FenceFeedback(TimestampMixin, Base):
    """家长提交的围栏误判反馈，供 CMS 复核失效样本。"""
    __tablename__ = "fence_feedback"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), index=True)
    message_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id"), nullable=True)
    fence_event_id: Mapped[int | None] = mapped_column(ForeignKey("fence_events.id"), nullable=True)
    reporter_role: Mapped[str] = mapped_column(String(20), default="guardian")
    reporter_id: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(30), default="false_positive")
    note: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(20), default="open")  # open|reviewed|dismissed
    reviewed_by: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ActiveTime(TimestampMixin, Base):
    """学生每日真实使用时长（端侧心跳上报累计）。P1 时长管控的数据源。"""
    __tablename__ = "active_times"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)
    day: Mapped[str] = mapped_column(String(10), index=True)  # 本地日 YYYY-MM-DD（TZ_OFFSET_HOURS 换算）
    seconds: Mapped[int] = mapped_column(Integer, default=0)


class Favorite(TimestampMixin, Base):
    """学习沉淀（P2 最小版）：学生收藏的对话消息（含原文，公式可复用）。"""
    __tablename__ = "favorites"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"))
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id"), unique=True)
    role: Mapped[str] = mapped_column(String(10))
    content: Mapped[str] = mapped_column(Text)  # 收藏时快照


class AdminUser(TimestampMixin, Base):
    """CMS 管理员（P2 RBAC）：super=全部权限；admin=运营管理；support=客服只读。

    登录后发 session_token（存库比对）；ADMIN_TOKENS 环境变量仍作为 super 后门。
    """
    __tablename__ = "admin_users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    password_hash: Mapped[str] = mapped_column(String(64))  # sha256
    role: Mapped[str] = mapped_column(String(20), default="admin")  # super | admin | support (ops兼容)
    session_token: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    note: Mapped[str] = mapped_column(String(100), default="")


class AdminLog(TimestampMixin, Base):
    """管理员操作日志：敏感操作（赠送/扣除/分组变更）全程留痕。"""
    __tablename__ = "admin_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    admin: Mapped[str] = mapped_column(String(50))
    action: Mapped[str] = mapped_column(String(40))
    detail: Mapped[str] = mapped_column(Text, default="")


class Subscription(TimestampMixin, Base):
    """家庭订阅：注册即开 30 天免费试用；到期未续费则学生端被拦截（P0 商业闭环）。

    一family一行（当前有效订阅）；支付通道骨架期为 mock，生产接微信/支付宝（需商户资质）。
    """
    __tablename__ = "subscriptions"
    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"), unique=True)
    plan: Mapped[str] = mapped_column(String(20), default="free_trial")  # free_trial | monthly
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    paid_amount: Mapped[float] = mapped_column(default=0.0)   # 累计实付（元）
    paid_amount_cents: Mapped[int] = mapped_column(Integer, default=0)
    provider: Mapped[str] = mapped_column(String(20), default="mock")  # mock|wechat|alipay
    seat_count: Mapped[int] = mapped_column(Integer, default=1)
    base_price_snapshot: Mapped[float] = mapped_column(Float, default=66.0)
    additional_seat_price_snapshot: Mapped[float] = mapped_column(Float, default=33.0)
    base_price_snapshot_cents: Mapped[int] = mapped_column(Integer, default=6600)
    additional_seat_price_snapshot_cents: Mapped[int] = mapped_column(Integer, default=3300)


class PricingConfig(TimestampMixin, Base):
    """CMS 生效的订阅策略；新家庭/新订单读取当前版本。"""
    __tablename__ = "pricing_configs"
    id: Mapped[int] = mapped_column(primary_key=True)
    base_monthly_price: Mapped[float] = mapped_column(Float, default=66.0)
    additional_seat_price: Mapped[float] = mapped_column(Float, default=33.0)
    # Integer cents are the source of truth; yuan float columns remain as a
    # read-compatible mirror for existing deployments and clients.
    base_monthly_price_cents: Mapped[int] = mapped_column(Integer, default=6600)
    additional_seat_price_cents: Mapped[int] = mapped_column(Integer, default=3300)
    trial_days: Mapped[int] = mapped_column(Integer, default=30)
    post_trial_daily_free_count: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1, unique=True)


class SubscriptionOrder(TimestampMixin, Base):
    __tablename__ = "subscription_orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"), index=True)
    kind: Mapped[str] = mapped_column(String(30))  # subscription|seat_add|grant|revoke|refund
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    amount_cents: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    price_snapshot: Mapped[str] = mapped_column(Text, default="{}")
    idempotency_key: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)


class Notification(TimestampMixin, Base):
    """家长通知：安全告警（不可关闭）/围栏事件/额度/系统。P0 安全闭环。"""
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"), index=True)
    type: Mapped[str] = mapped_column(String(20), index=True)  # security|fence|quota|system
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    title: Mapped[str] = mapped_column(String(100))
    body: Mapped[str] = mapped_column(Text, default="")
    conversation_id: Mapped[int | None] = mapped_column(ForeignKey("conversations.id"), nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)


class LLMGroup(TimestampMixin, Base):
    """LLM 分组：CMS 可配置的模型分组（provider+模型+Key 引用），支持灰度/切换/降级。

    api_key 存明文仅限开发环境骨架；生产应存密管引用（key_ref），此处保留字段双轨。
    is_active: 同一时刻只有一个分组生效（chat 端点读取该分组）。
    """
    __tablename__ = "llm_groups"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    provider: Mapped[str] = mapped_column(String(20))          # glm|deepseek|kimi|openrouter
    chat_model: Mapped[str] = mapped_column(String(80))
    fence_model: Mapped[str] = mapped_column(String(80))
    api_key: Mapped[str] = mapped_column(String(200), default="")
    daily_message_cap: Mapped[int] = mapped_column(Integer, default=0)  # 0=用全局
    note: Mapped[str] = mapped_column(String(200), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    # 标签绑定（唯一）：设置后，持此标签的家庭路由到本分组（优先级高于全局 is_active）
    tag: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True)
    teacher_name: Mapped[str] = mapped_column(String(50), default="AI 老师")
    teacher_avatar_url: Mapped[str] = mapped_column(String(500), default="")
    teacher_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    teacher_sort_order: Mapped[int] = mapped_column(Integer, default=0)
    post_trial_free_enabled: Mapped[bool] = mapped_column(Boolean, default=False)


class UsageLog(TimestampMixin, Base):
    """模型用量：成本模型的实际数据来源（对接 cost-model.xlsx 的 token 假设）。"""
    __tablename__ = "usage_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int | None] = mapped_column(ForeignKey("students.id"), nullable=True)
    purpose: Mapped[str] = mapped_column(String(20))   # chat | fence_classify | fence_second
    provider: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(String(50))
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    cost: Mapped[float] = mapped_column(default=0.0)


class StudentGrade(TimestampMixin, Base):
    __tablename__ = "student_grades"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)
    subject: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(100), default="")
    exam_date: Mapped[str] = mapped_column(String(10))
    term: Mapped[str] = mapped_column(String(30), default="")
    score: Mapped[float] = mapped_column(Float)
    max_score: Mapped[float] = mapped_column(Float)
    grade_type: Mapped[str] = mapped_column(String(20), default="exam")
    note: Mapped[str] = mapped_column(Text, default="")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_version: Mapped[int] = mapped_column(Integer, default=1)


class StudentGradeVersion(TimestampMixin, Base):
    __tablename__ = "student_grade_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    grade_id: Mapped[int] = mapped_column(ForeignKey("student_grades.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    subject: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(100), default="")
    exam_date: Mapped[str] = mapped_column(String(10))
    term: Mapped[str] = mapped_column(String(30), default="")
    score: Mapped[float] = mapped_column(Float)
    max_score: Mapped[float] = mapped_column(Float)
    grade_type: Mapped[str] = mapped_column(String(20), default="exam")
    note: Mapped[str] = mapped_column(Text, default="")
    edited_by_role: Mapped[str] = mapped_column(String(20))
    edited_by_id: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(200), default="")
    __table_args__ = (UniqueConstraint("grade_id", "version", name="uq_grade_version"),)


class AcademicAssessment(TimestampMixin, Base):
    __tablename__ = "academic_assessments"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)
    period_from: Mapped[str] = mapped_column(String(10))
    period_to: Mapped[str] = mapped_column(String(10))
    input_data_version: Mapped[str] = mapped_column(String(200), default="")
    model: Mapped[str] = mapped_column(String(100), default="")
    status: Mapped[str] = mapped_column(String(20), default="ready")
    result_json: Mapped[str] = mapped_column(Text, default="{}")


class WellbeingAssessment(TimestampMixin, Base):
    __tablename__ = "wellbeing_assessments"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)
    period_from: Mapped[str] = mapped_column(String(10))
    period_to: Mapped[str] = mapped_column(String(10))
    input_data_version: Mapped[str] = mapped_column(String(200), default="")
    model: Mapped[str] = mapped_column(String(100), default="")
    status: Mapped[str] = mapped_column(String(20), default="ready")
    result_json: Mapped[str] = mapped_column(Text, default="{}")
    ack_status: Mapped[str] = mapped_column(String(20), default="pending")


class AssessmentAudit(TimestampMixin, Base):
    __tablename__ = "assessment_audits"
    id: Mapped[int] = mapped_column(primary_key=True)
    assessment_type: Mapped[str] = mapped_column(String(20))
    assessment_id: Mapped[int] = mapped_column(Integer)
    actor_role: Mapped[str] = mapped_column(String(20))
    actor_id: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(30))
