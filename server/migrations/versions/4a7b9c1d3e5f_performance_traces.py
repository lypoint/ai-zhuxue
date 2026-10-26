"""Request attempt timings, separated by trusted server and browser sources."""
from alembic import op
import sqlalchemy as sa

revision = "4a7b9c1d3e5f"
down_revision = "3f6a8b0c2d4e"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("performance_traces",
        sa.Column("trace_id", sa.String(36), primary_key=True),
        sa.Column("source", sa.String(10), primary_key=True),
        sa.Column("family_id", sa.Integer(), sa.ForeignKey("families.id"), primary_key=True),
        sa.Column("student_id", sa.Integer(), nullable=True),
        sa.Column("message_id", sa.Integer(), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("operation", sa.String(20), nullable=False),
        sa.Column("node", sa.String(32), nullable=False),
        sa.Column("variant", sa.String(20), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("mode", sa.String(12), nullable=False),
        sa.Column("input_kind", sa.String(10), nullable=False),
        sa.Column("result", sa.String(12), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metrics", sa.Text(), nullable=False))
    op.create_index("ix_performance_traces_occurred_at", "performance_traces", ["occurred_at"])


def downgrade():
    op.drop_table("performance_traces")
