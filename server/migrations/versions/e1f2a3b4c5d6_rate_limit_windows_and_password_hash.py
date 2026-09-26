"""Shared rate-limit windows and stronger admin password hashes."""

from alembic import op
import sqlalchemy as sa

revision = "e1f2a3b4c5d6"
down_revision = "c0d1e2f3a4b5"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "rate_limit_windows",
        sa.Column("bucket_key", sa.String(160), primary_key=True),
        sa.Column("window_start", sa.Integer(), nullable=False),
        sa.Column("hits", sa.Integer(), nullable=False),
    )
    op.create_index("ix_rate_limit_windows_window_start", "rate_limit_windows", ["window_start"])
    with op.batch_alter_table("admin_users") as batch:
        batch.alter_column("password_hash", type_=sa.String(160), existing_type=sa.String(64), existing_nullable=False)


def downgrade():
    with op.batch_alter_table("admin_users") as batch:
        batch.alter_column("password_hash", type_=sa.String(64), existing_type=sa.String(160), existing_nullable=False)
    op.drop_index("ix_rate_limit_windows_window_start", table_name="rate_limit_windows")
    op.drop_table("rate_limit_windows")
