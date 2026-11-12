"""Persist first-registration channel and device; legacy values remain unknown."""
from alembic import op
import sqlalchemy as sa

revision = "8c0d2e4f6a91"
down_revision = "7a9c2e4f6b80"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("families", sa.Column("registration_channel", sa.String(20), nullable=True))
    op.add_column("families", sa.Column("registration_device", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("families", "registration_device")
    op.drop_column("families", "registration_channel")
