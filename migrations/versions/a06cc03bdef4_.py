"""empty message

Revision ID: a06cc03bdef4
Revises: 4b813bbbd8ef
Create Date: 2017-03-15 22:47:07.462793

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a06cc03bdef4'
down_revision = '4b813bbbd8ef'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('localtops',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('protocol_id', sa.Integer(), nullable=True),
    sa.Column('defaulttop_id', sa.Integer(), nullable=True),
    sa.Column('description', sa.String(), nullable=True),
    sa.ForeignKeyConstraint(['defaulttop_id'], ['defaulttops.id'], ),
    sa.ForeignKeyConstraint(['protocol_id'], ['protocols.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('localtops')
    # ### end Alembic commands ###
