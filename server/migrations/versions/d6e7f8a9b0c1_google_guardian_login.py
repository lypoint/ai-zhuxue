"""Allow Google identities without changing existing phone accounts."""
from alembic import op
import sqlalchemy as sa

revision = "d6e7f8a9b0c1"
down_revision = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("guardians") as batch:
        batch.alter_column("phone", existing_type=sa.String(20), nullable=True)
        batch.add_column(sa.Column("google_sub", sa.String(255), nullable=True))
        batch.create_unique_constraint("uq_guardians_google_sub", ["google_sub"])


def downgrade():
    if op.get_bind().execute(sa.text("SELECT 1 FROM guardians WHERE phone IS NULL LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade while Google-only guardian accounts exist")
    with op.batch_alter_table("guardians") as batch:
        batch.drop_constraint("uq_guardians_google_sub", type_="unique")
        batch.drop_column("google_sub")
        batch.alter_column("phone", existing_type=sa.String(20), nullable=False)
