"""Managed password accounts and family access revocation."""
from alembic import op
import sqlalchemy as sa

revision = "d7e8f9a0b1c2"
down_revision = "d6e7f8a9b0c1"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("families") as batch:
        batch.add_column(sa.Column("access_disabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    with op.batch_alter_table("guardians") as batch:
        batch.add_column(sa.Column("username", sa.String(32), nullable=True))
        batch.add_column(sa.Column("password_hash", sa.String(255), nullable=True))
        batch.add_column(sa.Column("is_review", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.create_unique_constraint("uq_guardians_username", ["username"])


def downgrade():
    if op.get_bind().execute(sa.text("SELECT 1 FROM guardians WHERE username IS NOT NULL LIMIT 1")).first():
        raise RuntimeError("Remove managed password accounts before downgrading")
    with op.batch_alter_table("guardians") as batch:
        batch.drop_constraint("uq_guardians_username", type_="unique")
        batch.drop_column("is_review")
        batch.drop_column("password_hash")
        batch.drop_column("username")
    with op.batch_alter_table("families") as batch:
        batch.drop_column("access_disabled")
