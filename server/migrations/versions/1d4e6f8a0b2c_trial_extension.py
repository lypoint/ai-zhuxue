"""Preserve remaining trial time separately from provider billing dates."""
from alembic import op
import sqlalchemy as sa

revision = "1d4e6f8a0b2c"
down_revision = "0c3e7a9b2d41"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("subscriptions", sa.Column("trial_extension_claimed", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("store_subscriptions", sa.Column("trial_extension_seconds", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("store_subscriptions", sa.Column("next_billing_at", sa.DateTime(timezone=True), nullable=True))
    # Existing purchases retain their original contract; new restores must not mint a bonus.
    op.execute("UPDATE subscriptions SET trial_extension_claimed = true WHERE plan <> 'free_trial' OR family_id IN (SELECT family_id FROM store_subscriptions)")


def downgrade():
    op.drop_column("store_subscriptions", "next_billing_at")
    op.drop_column("store_subscriptions", "trial_extension_seconds")
    op.drop_column("subscriptions", "trial_extension_claimed")
