"""Child-specific learning controls; null preserves legacy family defaults."""
from alembic import op
import sqlalchemy as sa

revision = "3f6a8b0c2d4e"
down_revision = "2e5f7a9b1c3d"
branch_labels = None
depends_on = None


def upgrade():
    for name, kind in [("daily_message_cap", sa.Integer), ("daily_minutes_cap", sa.Integer),
                       ("quiet_enabled", sa.Boolean), ("quiet_start", sa.Integer),
                       ("quiet_end", sa.Integer), ("notify_fence", sa.Boolean)]:
        op.add_column("students", sa.Column(name, kind(), nullable=True))


def downgrade():
    for name in ["notify_fence", "quiet_end", "quiet_start", "quiet_enabled", "daily_minutes_cap", "daily_message_cap"]:
        op.drop_column("students", name)
