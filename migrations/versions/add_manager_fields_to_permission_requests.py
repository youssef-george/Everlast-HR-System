"""add manager fields to permission requests

Revision ID: add_manager_fields_permission
Revises: add_notes_table
Create Date: 2025-12-22 13:33:26.274335

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_manager_fields_permission'
down_revision = 'add_notes_table'
branch_labels = None
depends_on = None


def upgrade():
    # Add manager approval fields to permission_requests table
    with op.batch_alter_table('permission_requests', schema=None) as batch_op:
        batch_op.add_column(sa.Column('manager_status', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('manager_comment', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('manager_updated_at', sa.DateTime(), nullable=True))
    
    # Set default values for existing records
    # For records where admin_status='approved', set manager_status='approved' to maintain data consistency
    # For records where admin_status='pending' or 'rejected', set manager_status='pending'
    op.execute("""
        UPDATE permission_requests 
        SET manager_status = CASE 
            WHEN admin_status = 'approved' THEN 'approved'
            ELSE 'pending'
        END
        WHERE manager_status IS NULL
    """)
    
    # Set default value for new records
    with op.batch_alter_table('permission_requests', schema=None) as batch_op:
        batch_op.alter_column('manager_status',
                            existing_type=sa.String(length=20),
                            nullable=False,
                            server_default='pending')


def downgrade():
    # Remove manager approval fields
    with op.batch_alter_table('permission_requests', schema=None) as batch_op:
        batch_op.drop_column('manager_updated_at')
        batch_op.drop_column('manager_comment')
        batch_op.drop_column('manager_status')
