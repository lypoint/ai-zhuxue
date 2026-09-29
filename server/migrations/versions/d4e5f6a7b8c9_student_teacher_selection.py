"""Remember each student's last selected teacher."""

from alembic import op
import sqlalchemy as sa


revision = "d4e5f6a7b8c9"
down_revision = "c2d3e4f5a6b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("students", sa.Column("last_teacher_group_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("students", "last_teacher_group_id")
