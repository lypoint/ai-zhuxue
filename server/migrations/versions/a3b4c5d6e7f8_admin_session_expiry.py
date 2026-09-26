"""Admin session token expiry."""

from alembic import op
import sqlalchemy as sa

revision = "a3b4c5d6e7f8"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("admin_users") as batch:
        batch.add_column(sa.Column("session_expires_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    with op.batch_alter_table("admin_users") as batch:
        batch.drop_column("session_expires_at")
