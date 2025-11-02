"""Add manager_id to User model

Revision ID: a240031710fa
Revises: add_deleted_user_table
Create Date: 2025-10-22 17:07:21.400381

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a240031710fa'
down_revision = 'add_deleted_user_table'
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
