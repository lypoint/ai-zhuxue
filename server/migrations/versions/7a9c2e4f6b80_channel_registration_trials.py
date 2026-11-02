"""Restore domestic registration trials; Google registrations remain three days."""
from alembic import op

revision = "7a9c2e4f6b80"
down_revision = "5b8c0d2e4f60"
branch_labels = None
depends_on = None


def upgrade():
    # Change the default for future domestic families, not historical entitlements/configs.
    op.execute("UPDATE pricing_configs SET trial_days = 30 WHERE trial_days = 3 AND id = (SELECT id FROM pricing_configs ORDER BY version DESC LIMIT 1)")


def downgrade():
    op.execute("UPDATE pricing_configs SET trial_days = 3 WHERE trial_days = 30 AND id = (SELECT id FROM pricing_configs ORDER BY version DESC LIMIT 1)")
