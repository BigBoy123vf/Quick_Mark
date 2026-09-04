"""add course requires_location flag

Revision ID: e2c6a4f8d1b3
Revises: d5f8b3c1a9e7
Create Date: 2026-09-04 03:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e2c6a4f8d1b3'
down_revision = 'd5f8b3c1a9e7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('courses', schema=None) as batch_op:
        batch_op.add_column(sa.Column('requires_location', sa.Boolean(), nullable=False, server_default=sa.true()))
        batch_op.alter_column('requires_location', server_default=None)


def downgrade():
    with op.batch_alter_table('courses', schema=None) as batch_op:
        batch_op.drop_column('requires_location')
