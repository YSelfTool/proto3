"""empty message

Revision ID: 97cf1913e60d
Revises: bbc1782c0999
Create Date: 2017-02-22 23:36:29.467493

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '97cf1913e60d'
down_revision = 'bbc1782c0999'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('tops', sa.Column('number', sa.Integer(), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('tops', 'number')
    # ### end Alembic commands ###
