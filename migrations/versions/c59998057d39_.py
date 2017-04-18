"""empty message

Revision ID: c59998057d39
Revises: 70547c924023
Create Date: 2017-04-18 13:39:05.342669

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c59998057d39'
down_revision = '70547c924023'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('defaulttops', sa.Column('description', sa.String(), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('defaulttops', 'description')
    # ### end Alembic commands ###
