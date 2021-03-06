"""empty message

Revision ID: 8fdd381e6a2a
Revises: cd972745eb09
Create Date: 2017-03-09 03:44:54.631531

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8fdd381e6a2a'
down_revision = 'cd972745eb09'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('protocols', sa.Column('pad_identifier', sa.String(), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('protocols', 'pad_identifier')
    # ### end Alembic commands ###
