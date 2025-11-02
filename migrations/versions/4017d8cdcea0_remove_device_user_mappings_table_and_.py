"""Remove device user mappings table and simplify sync logic

Revision ID: 4017d8cdcea0
Revises: 8f63119d258c
Create Date: 2025-10-02 11:25:54.606852

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4017d8cdcea0'
down_revision = '8f63119d258c'
branch_labels = None
depends_on = None


def upgrade():
    # Drop the device_user_mappings table
    op.drop_table('device_user_mappings')


def downgrade():
    # Recreate the device_user_mappings table
    op.create_table('device_user_mappings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('device_id', sa.Integer(), nullable=False),
        sa.Column('device_user_id', sa.String(length=50), nullable=False),
        sa.Column('system_user_id', sa.Integer(), nullable=False),
        sa.Column('is_conflict_resolved', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['device_id'], ['device_settings.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['system_user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('device_id', 'device_user_id', name='unique_device_user_mapping')
    )
    op.create_index('idx_device_user_mapping', 'device_user_mappings', ['device_id', 'device_user_id'], unique=False)
