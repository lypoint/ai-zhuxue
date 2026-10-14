"""Store subscriptions and durable verified notification inbox."""
from alembic import op
import sqlalchemy as sa

revision = "c3d4e5f6a7b8"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("store_accounts", sa.Column("family_id", sa.Integer(), sa.ForeignKey("families.id"), primary_key=True),
                    sa.Column("account_token", sa.String(36), nullable=False, unique=True),
                    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("store_subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("family_id", sa.Integer(), sa.ForeignKey("families.id"), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("chain_key", sa.String(64), nullable=False),
        sa.Column("linked_chain", sa.String(64), nullable=True),
        sa.Column("encrypted_token", sa.Text(), nullable=False),
        sa.Column("product_id", sa.String(200), nullable=False),
        sa.Column("seat_count", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(40), nullable=False),
        sa.Column("auto_renew", sa.Boolean(), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("channel", "chain_key", name="uq_store_chain"))
    op.create_index("ix_store_subscriptions_family_id", "store_subscriptions", ["family_id"])
    op.create_table("store_events", sa.Column("event_key", sa.String(100), primary_key=True),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("encrypted_reference", sa.Text(), nullable=False),
        sa.Column("processed", sa.Boolean(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))

    op.create_index("ix_store_events_next_attempt_at", "store_events", ["next_attempt_at"])
    op.create_table("store_transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("family_id", sa.Integer(), sa.ForeignKey("families.id"), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("transaction_id", sa.String(100), nullable=False),
        sa.Column("chain_key", sa.String(64), nullable=False),
        sa.Column("product_id", sa.String(200), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(40), nullable=False),
        sa.Column("price_milliunits", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(3), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("channel", "transaction_id", name="uq_store_transaction"))
    op.create_index("ix_store_transactions_family_id", "store_transactions", ["family_id"])


def downgrade():
    op.drop_table("store_transactions")
    op.drop_table("store_events")
    op.drop_table("store_subscriptions")
    op.drop_table("store_accounts")
