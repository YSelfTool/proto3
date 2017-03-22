"""empty message

Revision ID: 4651698510d7
Revises: a06cc03bdef4
Create Date: 2017-03-22 21:42:04.880972

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4651698510d7'
down_revision = 'a06cc03bdef4'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('defaultmetas', sa.Column('internal', sa.Boolean(), nullable=True))
    op.add_column('metas', sa.Column('internal', sa.Boolean(), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('metas', 'internal')
    op.drop_column('defaultmetas', 'internal')
    # ### end Alembic commands ###
