"""Durable in-app account deletion requests."""
from alembic import op
import sqlalchemy as sa

revision = "d8e9f0a1b2c3"
down_revision = "d7e8f9a0b1c2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("account_deletion_requests",
                    sa.Column("family_id", sa.Integer(), sa.ForeignKey("families.id"), primary_key=True),
                    sa.Column("guardian_id", sa.Integer(), sa.ForeignKey("guardians.id"), nullable=False),
                    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
                    sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    if op.get_bind().execute(sa.text("SELECT 1 FROM account_deletion_requests LIMIT 1")).first():
        raise RuntimeError("Resolve and archive deletion requests before downgrading")
    op.drop_table("account_deletion_requests")
