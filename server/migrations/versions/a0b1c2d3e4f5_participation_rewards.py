"""Participation rewards, feedback history, and agreed reward fulfillment."""
from datetime import timedelta
from alembic import op
import sqlalchemy as sa

revision = "a0b1c2d3e4f5"
down_revision = "f9a0b1c2d3e4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("learning_feedback_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("students.id"), nullable=False),
        sa.Column("message_id", sa.Integer(), sa.ForeignKey("messages.id"), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_learning_feedback_events_student_id", "learning_feedback_events", ["student_id"])
    op.create_table("learning_day_rewards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("students.id"), nullable=False),
        sa.Column("day", sa.String(10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("student_id", "day"))
    op.create_index("ix_learning_day_rewards_student_id", "learning_day_rewards", ["student_id"])
    op.create_table("reward_agreements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("students.id"), nullable=False),
        sa.Column("guardian_id", sa.Integer(), sa.ForeignKey("guardians.id"), nullable=False),
        sa.Column("reward", sa.String(200), nullable=False),
        sa.Column("stars", sa.Integer(), nullable=False),
        sa.Column("fulfillment", sa.String(100), nullable=False),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("student_id", "request_id"))
    op.create_index("ix_reward_agreements_student_id", "reward_agreements", ["student_id"])
    with op.batch_alter_table("reward_redemptions") as batch:
        batch.add_column(sa.Column("agreement_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_redemption_agreement", "reward_agreements", ["agreement_id"], ["id"])
        batch.add_column(sa.Column("fulfillment", sa.String(100), nullable=False, server_default=""))
        batch.add_column(sa.Column("fulfilled_at", sa.DateTime(timezone=True), nullable=True))
    # Preserve existing feedback and balances; apply the more inclusive rule to historical days.
    from app.config import settings
    db = op.get_bind()
    metadata = sa.MetaData()
    old = sa.Table("learning_feedback", metadata, autoload_with=db)
    events = sa.Table("learning_feedback_events", metadata, autoload_with=db)
    rewards = sa.Table("learning_day_rewards", metadata, autoload_with=db)
    seen = set()
    for row in db.execute(sa.select(old)).mappings():
        db.execute(events.insert().values(student_id=row["student_id"], message_id=row["message_id"],
                                         action=row["action"], created_at=row["created_at"]))
        day = (row["created_at"] + timedelta(hours=settings.tz_offset_hours)).date().isoformat()
        key = (row["student_id"], day)
        if key not in seen:
            db.execute(rewards.insert().values(student_id=key[0], day=day, created_at=row["created_at"]))
            seen.add(key)


def downgrade():
    with op.batch_alter_table("reward_redemptions") as batch:
        batch.drop_constraint("fk_redemption_agreement", type_="foreignkey")
        batch.drop_column("agreement_id")
        batch.drop_column("fulfillment")
        batch.drop_column("fulfilled_at")
    op.drop_table("reward_agreements")
    op.drop_table("learning_day_rewards")
    op.drop_table("learning_feedback_events")
