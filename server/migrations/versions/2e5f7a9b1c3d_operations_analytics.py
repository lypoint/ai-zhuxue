"""First-party operations events."""
from alembic import op
import sqlalchemy as sa

revision = "2e5f7a9b1c3d"
down_revision = "1d4e6f8a0b2c"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("analytics_events",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("name", sa.String(40), nullable=False),
        sa.Column("family_id", sa.Integer(), sa.ForeignKey("families.id"), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("properties", sa.Text(), nullable=False))
    op.create_index("ix_analytics_event_time", "analytics_events", ["name", "occurred_at"])
    op.create_index("ix_analytics_family_time", "analytics_events", ["family_id", "occurred_at"])


def downgrade():
    op.drop_table("analytics_events")
