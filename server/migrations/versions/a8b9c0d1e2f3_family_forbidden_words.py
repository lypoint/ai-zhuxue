"""Add parent-defined forbidden words."""
from alembic import op
import sqlalchemy as sa

revision = "a8b9c0d1e2f3"
down_revision = "e7f8a9b0c1d2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("family_settings", sa.Column(
        "forbidden_words_json", sa.Text(), nullable=False, server_default="[]"))


def downgrade():
    op.drop_column("family_settings", "forbidden_words_json")
