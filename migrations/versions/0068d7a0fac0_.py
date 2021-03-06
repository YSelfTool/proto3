"""empty message

Revision ID: 0068d7a0fac0
Revises: 4bdc217932c3
Create Date: 2017-03-04 02:27:14.915941

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0068d7a0fac0'
down_revision = '4bdc217932c3'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('protocoltypes', sa.Column('allowed_networks', sa.String(), nullable=True))
    op.add_column('protocoltypes', sa.Column('restrict_networks', sa.Boolean(), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('protocoltypes', 'restrict_networks')
    op.drop_column('protocoltypes', 'allowed_networks')
    # ### end Alembic commands ###
