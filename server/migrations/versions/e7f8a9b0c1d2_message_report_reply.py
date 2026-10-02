"""Add CMS reply to feedback.

Revision ID: e7f8a9b0c1d2
Revises: d4e5f6a7b8c9
"""
from alembic import op
import sqlalchemy as sa

revision = "e7f8a9b0c1d2"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("fence_feedback", sa.Column("reply_text", sa.String(1000), nullable=False, server_default=""))


def downgrade():
    op.drop_column("fence_feedback", "reply_text")
