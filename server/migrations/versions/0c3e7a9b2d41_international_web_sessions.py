"""Family time zones and revocable browser sessions."""
from alembic import op
import sqlalchemy as sa

revision = "0c3e7a9b2d41"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("families", sa.Column("timezone", sa.String(100), nullable=True))
    op.add_column("families", sa.Column("previous_timezone", sa.String(100), nullable=True))
    op.add_column("families", sa.Column("timezone_changed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table("web_sessions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("family_id", sa.Integer(), sa.ForeignKey("families.id"), nullable=False),
        sa.Column("token_version", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.Integer(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_web_sessions_family_id", "web_sessions", ["family_id"])
    op.create_index("ix_web_sessions_expires_at", "web_sessions", ["expires_at"])


def downgrade():
    op.drop_table("web_sessions")
    op.drop_column("families", "timezone_changed_at")
    op.drop_column("families", "previous_timezone")
    op.drop_column("families", "timezone")
