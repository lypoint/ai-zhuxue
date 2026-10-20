"""Private image assets, model configurations and diagram jobs

Revision ID: 62f45b63b2d2
Revises: d8e9f0a1b2c3
Create Date: 2026-10-19 17:24:15.366429

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '62f45b63b2d2'
down_revision: Union[str, None] = 'd8e9f0a1b2c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:

    op.create_table('image_model_configs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('kind', sa.String(length=12), nullable=False),
    sa.Column('protocol', sa.String(length=24), nullable=False),
    sa.Column('base_url', sa.String(length=500), nullable=False),
    sa.Column('model_id', sa.String(length=120), nullable=False),
    sa.Column('api_key', sa.Text(), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('supports_edit', sa.Boolean(), nullable=False),
    sa.Column('revision', sa.Integer(), nullable=False),
    sa.Column('tested_revision', sa.Integer(), nullable=True),
    sa.Column('price_in', sa.Float(), nullable=False),
    sa.Column('price_out', sa.Float(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('image_jobs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('message_id', sa.Integer(), nullable=False),
    sa.Column('student_id', sa.Integer(), nullable=False),
    sa.Column('teacher_id', sa.Integer(), nullable=True),
    sa.Column('state', sa.String(length=16), nullable=False),
    sa.Column('snapshot_json', sa.Text(), nullable=False),
    sa.Column('plan_json', sa.Text(), nullable=False),
    sa.Column('asset_id', sa.String(length=32), nullable=True),
    sa.Column('error', sa.String(length=200), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['message_id'], ['messages.id'], ),
    sa.ForeignKeyConstraint(['student_id'], ['students.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('message_id')
    )
    with op.batch_alter_table('image_jobs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_image_jobs_state'), ['state'], unique=False)
        batch_op.create_index(batch_op.f('ix_image_jobs_student_id'), ['student_id'], unique=False)

    op.create_table('media_assets',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('student_id', sa.Integer(), nullable=True),
    sa.Column('message_id', sa.Integer(), nullable=True),
    sa.Column('upload_key', sa.String(length=300), nullable=False),
    sa.Column('object_key', sa.String(length=300), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('mime_type', sa.String(length=40), nullable=False),
    sa.Column('byte_size', sa.Integer(), nullable=False),
    sa.Column('width', sa.Integer(), nullable=False),
    sa.Column('height', sa.Integer(), nullable=False),
    sa.Column('analysis_json', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['message_id'], ['messages.id'], ),
    sa.ForeignKeyConstraint(['student_id'], ['students.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('object_key')
    )
    with op.batch_alter_table('media_assets', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_media_assets_message_id'), ['message_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_media_assets_student_id'), ['student_id'], unique=False)

    with op.batch_alter_table('llm_groups', schema=None) as batch_op:
        batch_op.add_column(sa.Column('vision_test_signature', sa.String(length=64), server_default='', nullable=False))
        batch_op.add_column(sa.Column('image_input_mode', sa.String(length=12), server_default='off', nullable=False))
        batch_op.add_column(sa.Column('vision_config_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('image_config_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('diagram_enabled', sa.Boolean(), server_default=sa.text('(false)'), nullable=False))
        batch_op.add_column(sa.Column('auto_diagram', sa.Boolean(), server_default=sa.text('(false)'), nullable=False))
        batch_op.add_column(sa.Column('image_daily_cap', sa.Integer(), server_default='10', nullable=False))
        batch_op.create_foreign_key('fk_llm_image_config', 'image_model_configs', ['image_config_id'], ['id'])
        batch_op.create_foreign_key('fk_llm_vision_config', 'image_model_configs', ['vision_config_id'], ['id'])

    with op.batch_alter_table('messages', schema=None) as batch_op:
        batch_op.add_column(sa.Column('blocks_json', sa.Text(), server_default='[]', nullable=False))




def downgrade() -> None:
    for table in ("media_assets", "image_jobs", "image_model_configs"):
        if op.get_bind().execute(sa.text(f"SELECT 1 FROM {table} LIMIT 1")).first():
            raise RuntimeError("Export and remove image data before downgrading")

    with op.batch_alter_table('messages', schema=None) as batch_op:
        batch_op.drop_column('blocks_json')

    with op.batch_alter_table('llm_groups', schema=None) as batch_op:
        batch_op.drop_constraint('fk_llm_image_config', type_='foreignkey')
        batch_op.drop_constraint('fk_llm_vision_config', type_='foreignkey')
        batch_op.drop_column('image_daily_cap')
        batch_op.drop_column('auto_diagram')
        batch_op.drop_column('diagram_enabled')
        batch_op.drop_column('image_config_id')
        batch_op.drop_column('vision_config_id')
        batch_op.drop_column('image_input_mode')
        batch_op.drop_column('vision_test_signature')

    with op.batch_alter_table('media_assets', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_media_assets_student_id'))
        batch_op.drop_index(batch_op.f('ix_media_assets_message_id'))

    op.drop_table('media_assets')
    with op.batch_alter_table('image_jobs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_image_jobs_student_id'))
        batch_op.drop_index(batch_op.f('ix_image_jobs_state'))

    op.drop_table('image_jobs')
    op.drop_table('image_model_configs')
