"""add class schedule slots

Revision ID: 9f3c2a7d5e41
Revises: 68112610ff18
Create Date: 2026-08-21 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9f3c2a7d5e41'
down_revision = '68112610ff18'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('class_schedule_slots',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('course_id', sa.Integer(), nullable=False),
    sa.Column('day_of_week', sa.Integer(), nullable=False),
    sa.Column('start_time', sa.Time(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('class_schedule_slots')
