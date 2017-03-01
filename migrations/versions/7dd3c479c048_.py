"""empty message

Revision ID: 7dd3c479c048
Revises: ab996d2365af
Create Date: 2017-03-01 03:54:18.283388

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7dd3c479c048'
down_revision = 'ab996d2365af'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('protocoltypes', sa.Column('modify_group', sa.String(), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('protocoltypes', 'modify_group')
    # ### end Alembic commands ###
