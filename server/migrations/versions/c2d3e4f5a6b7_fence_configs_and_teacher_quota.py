"""Separate fence configurations and teacher daily free quotas."""

from alembic import op
import sqlalchemy as sa

revision = "c2d3e4f5a6b7"
down_revision = "a3b4c5d6e7f8"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "fence_configs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(50), nullable=False, unique=True),
        sa.Column("base_url", sa.String(500), nullable=False),
        sa.Column("api_key", sa.String(500), nullable=False),
        sa.Column("model_id", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    with op.batch_alter_table("llm_groups") as batch:
        batch.add_column(sa.Column("base_url", sa.String(500), nullable=False, server_default=""))
        batch.add_column(sa.Column("fence_config_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("post_trial_daily_free_count", sa.Integer(), nullable=False, server_default="0"))
        batch.alter_column("chat_model", existing_type=sa.String(80), type_=sa.String(120))
        batch.alter_column("api_key", existing_type=sa.String(200), type_=sa.String(500))
        batch.create_foreign_key("fk_llm_groups_fence_config", "fence_configs", ["fence_config_id"], ["id"])
    op.execute(
        "UPDATE llm_groups SET post_trial_daily_free_count = 1 "
        "WHERE post_trial_free_enabled = TRUE"
    )
    with op.batch_alter_table("usage_logs") as batch:
        batch.alter_column("model", existing_type=sa.String(50), type_=sa.String(120))


def downgrade():
    with op.batch_alter_table("usage_logs") as batch:
        batch.alter_column("model", existing_type=sa.String(120), type_=sa.String(50))
    with op.batch_alter_table("llm_groups") as batch:
        batch.drop_constraint("fk_llm_groups_fence_config", type_="foreignkey")
        batch.alter_column("chat_model", existing_type=sa.String(120), type_=sa.String(80))
        batch.alter_column("api_key", existing_type=sa.String(500), type_=sa.String(200))
        batch.drop_column("post_trial_daily_free_count")
        batch.drop_column("fence_config_id")
        batch.drop_column("base_url")
    op.drop_table("fence_configs")
