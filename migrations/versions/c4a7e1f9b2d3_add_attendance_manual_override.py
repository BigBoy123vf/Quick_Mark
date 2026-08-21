"""add attendance manual override fields

Revision ID: c4a7e1f9b2d3
Revises: 9f3c2a7d5e41
Create Date: 2026-08-21 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c4a7e1f9b2d3'
down_revision = '9f3c2a7d5e41'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('attendance_records', schema=None) as batch_op:
        batch_op.add_column(sa.Column('override_reason', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('overridden_by_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('overridden_at', sa.DateTime(), nullable=True))
        batch_op.create_foreign_key(
            'fk_attendance_records_overridden_by_id_users', 'users', ['overridden_by_id'], ['id']
        )


def downgrade():
    with op.batch_alter_table('attendance_records', schema=None) as batch_op:
        batch_op.drop_constraint('fk_attendance_records_overridden_by_id_users', type_='foreignkey')
        batch_op.drop_column('overridden_at')
        batch_op.drop_column('overridden_by_id')
        batch_op.drop_column('override_reason')
