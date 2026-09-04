"""add course last-known session location

Revision ID: d5f8b3c1a9e7
Revises: c4a7e1f9b2d3
Create Date: 2026-09-04 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd5f8b3c1a9e7'
down_revision = 'c4a7e1f9b2d3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('courses', schema=None) as batch_op:
        batch_op.add_column(sa.Column('last_location_latitude', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('last_location_longitude', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('last_location_accuracy', sa.Float(), nullable=True))


def downgrade():
    with op.batch_alter_table('courses', schema=None) as batch_op:
        batch_op.drop_column('last_location_accuracy')
        batch_op.drop_column('last_location_longitude')
        batch_op.drop_column('last_location_latitude')
