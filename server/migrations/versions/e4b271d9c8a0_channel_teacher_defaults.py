"""Independent default teacher for each distribution channel."""
from alembic import op
import sqlalchemy as sa

revision = 'e4b271d9c8a0'
down_revision = '62f45b63b2d2'
branch_labels = None
depends_on = None


def upgrade():
    table = op.create_table('channel_teacher_defaults',
        sa.Column('channel', sa.String(20), primary_key=True),
        sa.Column('teacher_group_id', sa.Integer(),
                  sa.ForeignKey('llm_groups.id', ondelete='SET NULL'), nullable=True))
    connection = op.get_bind()
    for channel in ('wechat', 'appstore', 'googleplay'):
        teacher_id = connection.execute(sa.text('''
            SELECT id FROM llm_groups WHERE is_active = true AND teacher_enabled = true
            AND teacher_channel IN ('all', :channel) ORDER BY teacher_sort_order, id LIMIT 1
        '''), {'channel': channel}).scalar()
        connection.execute(table.insert().values(channel=channel, teacher_group_id=teacher_id))


def downgrade():
    op.drop_table('channel_teacher_defaults')
