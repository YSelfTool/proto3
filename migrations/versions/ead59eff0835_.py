"""empty message

Revision ID: ead59eff0835
Revises: 279bfa293885
Create Date: 2018-03-01 15:58:34.177099

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ead59eff0835'
down_revision = '279bfa293885'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('protocoltypes', sa.Column('latex_template', sa.String(), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('protocoltypes', 'latex_template')
    # ### end Alembic commands ###
