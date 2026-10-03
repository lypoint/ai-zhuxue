"""Store learning feedback and reward redemptions."""
from alembic import op
import sqlalchemy as sa

revision = "f9a0b1c2d3e4"
down_revision = "a8b9c0d1e2f3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("learning_feedback",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("students.id"), nullable=False),
        sa.Column("message_id", sa.Integer(), sa.ForeignKey("messages.id"), nullable=False, unique=True),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_learning_feedback_student_id", "learning_feedback", ["student_id"])
    op.create_table("reward_redemptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("students.id"), nullable=False),
        sa.Column("guardian_id", sa.Integer(), sa.ForeignKey("guardians.id"), nullable=False),
        sa.Column("reward", sa.String(200), nullable=False),
        sa.Column("stars", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("student_id", "request_id"))
    op.create_index("ix_reward_redemptions_student_id", "reward_redemptions", ["student_id"])


def downgrade():
    op.drop_table("reward_redemptions")
    op.drop_table("learning_feedback")
