"""store parent fence misclassification feedback for CMS review"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b9c0d1e2f3a4"
down_revision: Union[str, None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "fence_feedback" not in inspector.get_table_names():
        op.create_table(
            "fence_feedback",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("student_id", sa.Integer(), sa.ForeignKey("students.id"), nullable=False),
            sa.Column("conversation_id", sa.Integer(), sa.ForeignKey("conversations.id"), nullable=False),
            sa.Column("message_id", sa.Integer(), sa.ForeignKey("messages.id"), nullable=True),
            sa.Column("fence_event_id", sa.Integer(), sa.ForeignKey("fence_events.id"), nullable=True),
            sa.Column("reporter_role", sa.String(20), nullable=False, server_default="guardian"),
            sa.Column("reporter_id", sa.Integer(), nullable=False),
            sa.Column("kind", sa.String(30), nullable=False, server_default="false_positive"),
            sa.Column("note", sa.String(500), nullable=False, server_default=""),
            sa.Column("status", sa.String(20), nullable=False, server_default="open"),
            sa.Column("reviewed_by", sa.String(50), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_fence_feedback_student_id", "fence_feedback", ["student_id"])
        op.create_index("ix_fence_feedback_conversation_id", "fence_feedback", ["conversation_id"])


def downgrade() -> None:
    op.drop_index("ix_fence_feedback_conversation_id", table_name="fence_feedback")
    op.drop_index("ix_fence_feedback_student_id", table_name="fence_feedback")
    op.drop_table("fence_feedback")
