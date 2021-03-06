"""empty message

Revision ID: 4bdc217932c3
Revises: d5be0f66b32d
Create Date: 2017-03-01 05:19:03.947825

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4bdc217932c3'
down_revision = 'd5be0f66b32d'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('protocols', 'location')
    op.drop_column('protocols', 'author')
    op.drop_column('protocols', 'participants')
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('protocols', sa.Column('participants', sa.VARCHAR(), autoincrement=False, nullable=True))
    op.add_column('protocols', sa.Column('author', sa.VARCHAR(), autoincrement=False, nullable=True))
    op.add_column('protocols', sa.Column('location', sa.VARCHAR(), autoincrement=False, nullable=True))
    # ### end Alembic commands ###
