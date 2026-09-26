"""store monetary facts as integer RMB cents"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c0d1e2f3a4b5"
down_revision: Union[str, None] = "b9c0d1e2f3a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add(table: str, column: sa.Column) -> None:
    inspector = sa.inspect(op.get_bind())
    if column.name not in {c["name"] for c in inspector.get_columns(table)}:
        op.add_column(table, column)


def upgrade() -> None:
    _add("pricing_configs", sa.Column("base_monthly_price_cents", sa.Integer(), nullable=False, server_default="0"))
    _add("pricing_configs", sa.Column("additional_seat_price_cents", sa.Integer(), nullable=False, server_default="0"))
    _add("subscriptions", sa.Column("paid_amount_cents", sa.Integer(), nullable=False, server_default="0"))
    _add("subscriptions", sa.Column("base_price_snapshot_cents", sa.Integer(), nullable=False, server_default="0"))
    _add("subscriptions", sa.Column("additional_seat_price_snapshot_cents", sa.Integer(), nullable=False, server_default="0"))
    _add("subscription_orders", sa.Column("amount_cents", sa.Integer(), nullable=False, server_default="0"))
    # Backfill legacy decimal columns once. Existing cents defaults are only
    # placeholders for old rows and are replaced with the historical values.
    op.execute("UPDATE pricing_configs SET base_monthly_price_cents = CAST(ROUND(base_monthly_price * 100) AS INTEGER) WHERE base_monthly_price != 0")
    op.execute("UPDATE pricing_configs SET additional_seat_price_cents = CAST(ROUND(additional_seat_price * 100) AS INTEGER) WHERE additional_seat_price != 0")
    op.execute("UPDATE subscriptions SET paid_amount_cents = CAST(ROUND(paid_amount * 100) AS INTEGER) WHERE paid_amount != 0")
    op.execute("UPDATE subscriptions SET base_price_snapshot_cents = CAST(ROUND(base_price_snapshot * 100) AS INTEGER) WHERE base_price_snapshot != 0")
    op.execute("UPDATE subscriptions SET additional_seat_price_snapshot_cents = CAST(ROUND(additional_seat_price_snapshot * 100) AS INTEGER) WHERE additional_seat_price_snapshot != 0")
    op.execute("UPDATE subscription_orders SET amount_cents = CAST(ROUND(amount * 100) AS INTEGER) WHERE amount != 0")


def downgrade() -> None:
    op.drop_column("subscription_orders", "amount_cents")
    op.drop_column("subscriptions", "additional_seat_price_snapshot_cents")
    op.drop_column("subscriptions", "base_price_snapshot_cents")
    op.drop_column("subscriptions", "paid_amount_cents")
    op.drop_column("pricing_configs", "additional_seat_price_cents")
    op.drop_column("pricing_configs", "base_monthly_price_cents")
