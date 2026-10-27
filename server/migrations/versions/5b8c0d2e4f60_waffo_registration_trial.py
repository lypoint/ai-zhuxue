"""Set registration trials to three days; Waffo owns its separate subscription trial."""
from alembic import op

revision = "5b8c0d2e4f60"
down_revision = "4a7b9c1d3e5f"
branch_labels = None
depends_on = None


def upgrade():
    # Running installations read pricing from the database, not environment defaults.
    op.execute("UPDATE pricing_configs SET trial_days = 3 WHERE trial_days = 30")
    # Retain the ledger, but stop granting or reconciling retired test-provider rights.
    op.execute("UPDATE store_subscriptions SET state = 'revoked', auto_renew = false, trial_extension_seconds = 0, next_billing_at = NULL WHERE channel IN ('paddle_sandbox', 'creem_test')")
    op.execute("UPDATE store_events SET processed = true WHERE channel IN ('paddle_sandbox', 'creem_test')")


def downgrade():
    op.execute("UPDATE pricing_configs SET trial_days = 30 WHERE trial_days = 3")
