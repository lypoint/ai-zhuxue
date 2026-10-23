"""Store independent content fence settings for each child."""
from alembic import op
import sqlalchemy as sa

revision = "f1a2b3c4d5e6"
down_revision = "e4b271d9c8a0"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("students", sa.Column(
        "fence_level", sa.String(16), nullable=False, server_default="strict"))
    op.add_column("students", sa.Column(
        "forbidden_words_json", sa.Text(), nullable=False, server_default="[]"))
    # Preserve current restrictions once; future changes are independent per child.
    op.execute(sa.text("""UPDATE students SET forbidden_words_json = COALESCE(
        (SELECT forbidden_words_json FROM family_settings
         WHERE family_settings.family_id = students.family_id), '[]')
         WHERE active = true"""))


def downgrade():
    op.drop_column("students", "forbidden_words_json")
    op.drop_column("students", "fence_level")
