"""empty message

Revision ID: 0e5220a9f169
Revises: 188f389b2286
Create Date: 2017-02-26 15:53:41.410353

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0e5220a9f169'
down_revision = '188f389b2286'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('decisiondocuments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('decision_id', sa.Integer(), nullable=True),
    sa.Column('name', sa.String(), nullable=True),
    sa.Column('filename', sa.String(), nullable=True),
    sa.Column('is_compiled', sa.Boolean(), nullable=True),
    sa.Column('is_private', sa.Boolean(), nullable=True),
    sa.ForeignKeyConstraint(['decision_id'], ['decisions.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('decisiondocuments')
    # ### end Alembic commands ###
