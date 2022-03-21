"""Append extra column to Document

Revision ID: 7834767242e8
Revises: ead59eff0835
Create Date: 2022-03-21 11:46:20.368800

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7834767242e8'
down_revision = 'ead59eff0835'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('documents', sa.Column('is_extra', sa.Boolean(), default=False, nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('documents', 'is_extra')
    # ### end Alembic commands ###
