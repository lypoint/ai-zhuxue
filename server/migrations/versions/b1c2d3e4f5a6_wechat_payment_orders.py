"""Persist WeChat pending orders and unique provider transaction IDs."""
from alembic import op
import sqlalchemy as sa

revision = "b1c2d3e4f5a6"
down_revision = "a0b1c2d3e4f5"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("subscription_orders") as batch:
        batch.add_column(sa.Column("provider", sa.String(20), nullable=False, server_default="mock"))
        batch.add_column(sa.Column("out_trade_no", sa.String(32), nullable=True))
        batch.add_column(sa.Column("transaction_id", sa.String(64), nullable=True))
        batch.add_column(sa.Column("payment_params", sa.Text(), nullable=False, server_default="{}"))
        batch.create_unique_constraint("uq_subscription_order_trade", ["out_trade_no"])
        batch.create_unique_constraint("uq_subscription_order_transaction", ["transaction_id"])
    op.create_index("uq_family_pending_payment", "subscription_orders", ["family_id"], unique=True,
                    sqlite_where=sa.text("status = 'pending' AND provider IN ('demo', 'wechat')"),
                    postgresql_where=sa.text("status = 'pending' AND provider IN ('demo', 'wechat')"))


def downgrade():
    op.drop_index("uq_family_pending_payment", table_name="subscription_orders")
    with op.batch_alter_table("subscription_orders") as batch:
        batch.drop_constraint("uq_subscription_order_transaction", type_="unique")
        batch.drop_constraint("uq_subscription_order_trade", type_="unique")
        for name in ("payment_params", "transaction_id", "out_trade_no", "provider"):
            batch.drop_column(name)
