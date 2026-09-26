"""family growth, teacher profiles, soft deletion, grades and assessments"""
import os
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f6a4c2b7d901"
down_revision: Union[str, None] = "13c65af1ed08"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    def add(table, column):
        if column.name not in {c["name"] for c in inspector.get_columns(table)}:
            op.add_column(table, column)

    # SQLite cannot add a UNIQUE constraint with ALTER TABLE; add the nullable
    # column first and enforce uniqueness with an index below.
    add("students", sa.Column("installation_id", sa.String(64), nullable=True))
    add("fence_events", sa.Column("intent", sa.String(30), nullable=False, server_default=""))
    add("fence_events", sa.Column("safety_education", sa.Boolean(), nullable=False, server_default=sa.false()))
    add("bind_codes", sa.Column("target_student_id", sa.Integer(), nullable=True))
    add("bind_codes", sa.Column("purpose", sa.String(20), nullable=False, server_default="new_student"))
    add("bind_codes", sa.Column("used_at", sa.DateTime(timezone=True), nullable=True))
    add("bind_codes", sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True))
    add("conversations", sa.Column("student_deleted_at", sa.DateTime(timezone=True), nullable=True))
    add("conversations", sa.Column("student_deleted_by", sa.Integer(), nullable=True))
    add("conversations", sa.Column("deleted_reason", sa.String(200), nullable=False, server_default=""))
    add("conversations", sa.Column("teacher_group_id", sa.Integer(), nullable=True))
    add("conversations", sa.Column("teacher_name_snapshot", sa.String(50), nullable=False, server_default="AI 老师"))
    add("conversations", sa.Column("teacher_avatar_snapshot", sa.String(500), nullable=False, server_default=""))
    add("subscriptions", sa.Column("seat_count", sa.Integer(), nullable=False, server_default="1"))
    add("subscriptions", sa.Column("base_price_snapshot", sa.Float(), nullable=False, server_default="66"))
    add("subscriptions", sa.Column("additional_seat_price_snapshot", sa.Float(), nullable=False, server_default="33"))
    for col in (
        sa.Column("teacher_name", sa.String(50), nullable=False, server_default="AI 老师"),
        sa.Column("teacher_avatar_url", sa.String(500), nullable=False, server_default=""),
        sa.Column("teacher_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("teacher_sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("post_trial_free_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    ):
        add("llm_groups", col)

    # Existing deployments used device_id as the stable student identity.
    # Copy it once so logout/rebind upgrades do not create a second child.
    op.execute("UPDATE students SET installation_id = device_id WHERE installation_id IS NULL AND device_id IS NOT NULL")

    student_indexes = {i["name"] for i in inspector.get_indexes("students")}
    if "uq_students_installation_id" not in student_indexes:
        op.create_index("uq_students_installation_id", "students", ["installation_id"], unique=True)

    if "student_devices" not in inspector.get_table_names():
        op.create_table(
            "student_devices",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("student_id", sa.Integer(), sa.ForeignKey("students.id"), nullable=False),
            sa.Column("installation_id", sa.String(64), nullable=False, unique=True),
            sa.Column("device_name", sa.String(100), nullable=False, server_default=""),
            sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    # One child may have many revoked devices but only one current device.
    # Normalize legacy rows before adding the portable partial unique index.
    op.execute(
        "UPDATE student_devices SET is_current = FALSE "
        "WHERE is_current AND id NOT IN "
        "(SELECT MAX(id) FROM student_devices WHERE is_current GROUP BY student_id)"
    )
    device_indexes = {i["name"] for i in sa.inspect(bind).get_indexes("student_devices")}
    if "uq_student_current_device" not in device_indexes:
        op.create_index(
            "uq_student_current_device", "student_devices", ["student_id"], unique=True,
            sqlite_where=sa.text("is_current = 1"),
            postgresql_where=sa.text("is_current = true"),
        )
    if "pricing_configs" not in inspector.get_table_names():
        op.create_table(
            "pricing_configs", sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("base_monthly_price", sa.Float(), nullable=False, server_default="66"),
            sa.Column("additional_seat_price", sa.Float(), nullable=False, server_default="33"),
            sa.Column("trial_days", sa.Integer(), nullable=False, server_default="30"),
            sa.Column("post_trial_daily_free_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("version", sa.Integer(), nullable=False, unique=True, server_default="1"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    # Keep a deterministic first row so production registrations never race
    # on an empty configuration table. CMS can publish a new version later.
    bind.execute(
        sa.text(
            "INSERT INTO pricing_configs "
            "(base_monthly_price, additional_seat_price, trial_days, "
            "post_trial_daily_free_count, version, created_at) "
            "SELECT :base, :seat, :trial, :free, 1, CURRENT_TIMESTAMP "
            "WHERE NOT EXISTS (SELECT 1 FROM pricing_configs)"
        ),
        {
            "base": float(os.environ.get("PRICING_BASE_MONTHLY_PRICE", "66")),
            "seat": float(os.environ.get("PRICING_ADDITIONAL_SEAT_PRICE", "33")),
            "trial": int(os.environ.get("PRICING_TRIAL_DAYS", "30")),
            "free": int(os.environ.get("PRICING_POST_TRIAL_DAILY_FREE_COUNT", "0")),
        },
    )
    if "subscription_orders" not in inspector.get_table_names():
        op.create_table(
            "subscription_orders", sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("family_id", sa.Integer(), sa.ForeignKey("families.id"), nullable=False),
            sa.Column("kind", sa.String(30), nullable=False), sa.Column("amount", sa.Float(), nullable=False, server_default="0"),
            sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("price_snapshot", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("idempotency_key", sa.String(100), unique=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    if "student_grades" not in inspector.get_table_names():
        op.create_table(
            "student_grades", sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("student_id", sa.Integer(), sa.ForeignKey("students.id"), nullable=False),
            sa.Column("subject", sa.String(40), nullable=False), sa.Column("title", sa.String(100), nullable=False, server_default=""),
            sa.Column("exam_date", sa.String(10), nullable=False), sa.Column("term", sa.String(30), nullable=False, server_default=""),
            sa.Column("score", sa.Float(), nullable=False), sa.Column("max_score", sa.Float(), nullable=False),
            sa.Column("grade_type", sa.String(20), nullable=False, server_default="exam"), sa.Column("note", sa.Text(), nullable=False, server_default=""),
            sa.Column("deleted_at", sa.DateTime(timezone=True)), sa.Column("current_version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    if "student_grade_versions" not in inspector.get_table_names():
        op.create_table(
            "student_grade_versions", sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("grade_id", sa.Integer(), sa.ForeignKey("student_grades.id"), nullable=False), sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("subject", sa.String(40), nullable=False), sa.Column("title", sa.String(100), nullable=False, server_default=""),
            sa.Column("exam_date", sa.String(10), nullable=False), sa.Column("term", sa.String(30), nullable=False, server_default=""),
            sa.Column("score", sa.Float(), nullable=False), sa.Column("max_score", sa.Float(), nullable=False),
            sa.Column("grade_type", sa.String(20), nullable=False, server_default="exam"), sa.Column("note", sa.Text(), nullable=False, server_default=""),
            sa.Column("edited_by_role", sa.String(20), nullable=False), sa.Column("edited_by_id", sa.Integer(), nullable=False), sa.Column("reason", sa.String(200), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("grade_id", "version", name="uq_grade_version"),
        )
    for table, cols in {
        "academic_assessments": [
            sa.Column("id", sa.Integer(), primary_key=True), sa.Column("student_id", sa.Integer(), sa.ForeignKey("students.id"), nullable=False),
            sa.Column("period_from", sa.String(10), nullable=False), sa.Column("period_to", sa.String(10), nullable=False), sa.Column("input_data_version", sa.String(200), nullable=False, server_default=""), sa.Column("model", sa.String(100), nullable=False, server_default=""), sa.Column("status", sa.String(20), nullable=False, server_default="ready"), sa.Column("result_json", sa.Text(), nullable=False, server_default="{}"), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False)],
        "wellbeing_assessments": [
            sa.Column("id", sa.Integer(), primary_key=True), sa.Column("student_id", sa.Integer(), sa.ForeignKey("students.id"), nullable=False),
            sa.Column("period_from", sa.String(10), nullable=False), sa.Column("period_to", sa.String(10), nullable=False), sa.Column("input_data_version", sa.String(200), nullable=False, server_default=""), sa.Column("model", sa.String(100), nullable=False, server_default=""), sa.Column("status", sa.String(20), nullable=False, server_default="ready"), sa.Column("result_json", sa.Text(), nullable=False, server_default="{}"), sa.Column("ack_status", sa.String(20), nullable=False, server_default="pending"), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False)],
        "assessment_audits": [
            sa.Column("id", sa.Integer(), primary_key=True), sa.Column("assessment_type", sa.String(20), nullable=False), sa.Column("assessment_id", sa.Integer(), nullable=False), sa.Column("actor_role", sa.String(20), nullable=False), sa.Column("actor_id", sa.Integer(), nullable=False), sa.Column("action", sa.String(30), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False)],
    }.items():
        if table not in inspector.get_table_names():
            op.create_table(table, *cols)


def downgrade() -> None:
    for table in ("assessment_audits", "wellbeing_assessments", "academic_assessments", "student_grade_versions", "student_grades", "subscription_orders", "pricing_configs", "student_devices"):
        op.drop_table(table)
