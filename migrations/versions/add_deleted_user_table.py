"""Add DeletedUser table

Revision ID: add_deleted_user_table
Revises: eb2d1bc24a06
Create Date: 2025-10-02 18:55:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_deleted_user_table'
down_revision = 'eb2d1bc24a06'
branch_labels = None
depends_on = None


def upgrade():
    # Create deleted_users table
    op.create_table('deleted_users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fingerprint_number', sa.String(length=50), nullable=False),
        sa.Column('user_name', sa.String(length=100), nullable=True),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.Column('deleted_by', sa.Integer(), nullable=True),
        sa.Column('reason', sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(['deleted_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('fingerprint_number')
    )
    
    # Create indexes
    op.create_index('idx_deleted_user_fingerprint', 'deleted_users', ['fingerprint_number'])
    op.create_index('idx_deleted_user_deleted_at', 'deleted_users', ['deleted_at'])


def downgrade():
    # Drop indexes
    op.drop_index('idx_deleted_user_deleted_at', table_name='deleted_users')
    op.drop_index('idx_deleted_user_fingerprint', table_name='deleted_users')
    
    # Drop table
    op.drop_table('deleted_users')
