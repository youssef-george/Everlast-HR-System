"""add notes table

Revision ID: add_notes_table
Revises: 
Create Date: 2025-12-22 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_notes_table'
down_revision = 'add_activity_log'  # Update this with the latest migration revision
branch_labels = None
depends_on = None


def upgrade():
    # Create notes table
    op.create_table('notes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('created_by_id', sa.Integer(), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=False),
        sa.Column('comment', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes
    op.create_index('idx_note_user', 'notes', ['user_id'])
    op.create_index('idx_note_dates', 'notes', ['start_date', 'end_date'])
    op.create_index('idx_note_created_by', 'notes', ['created_by_id'])


def downgrade():
    # Drop indexes
    op.drop_index('idx_note_created_by', table_name='notes')
    op.drop_index('idx_note_dates', table_name='notes')
    op.drop_index('idx_note_user', table_name='notes')
    
    # Drop table
    op.drop_table('notes')
