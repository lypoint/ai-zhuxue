"""add explicit fence intent and safety education audit fields"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, None] = "f6a4c2b7d901"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {c["name"] for c in inspector.get_columns("fence_events")}
    if "intent" not in columns:
        op.add_column("fence_events", sa.Column("intent", sa.String(30), nullable=False, server_default=""))
    if "safety_education" not in columns:
        op.add_column("fence_events", sa.Column("safety_education", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("fence_events", "safety_education")
    op.drop_column("fence_events", "intent")
