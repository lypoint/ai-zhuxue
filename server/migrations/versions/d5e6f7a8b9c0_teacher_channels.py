"""Scope teachers to distribution channels; existing teachers remain shared."""
from alembic import op
import sqlalchemy as sa

revision = "d5e6f7a8b9c0"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("llm_groups", sa.Column("teacher_channel", sa.String(20),
                                        nullable=False, server_default="all"))


def downgrade():
    op.drop_column("llm_groups", "teacher_channel")
