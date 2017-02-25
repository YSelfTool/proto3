"""empty message

Revision ID: 495509e8f49a
Revises: 310d9ab321b8
Create Date: 2017-02-25 17:34:03.830014

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '495509e8f49a'
down_revision = '310d9ab321b8'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('protocols', sa.Column('content_private', sa.String(), nullable=True))
    op.add_column('protocols', sa.Column('content_public', sa.String(), nullable=True))
    op.drop_column('protocols', 'plain_text_private')
    op.drop_column('protocols', 'plain_text_public')
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('protocols', sa.Column('plain_text_public', sa.VARCHAR(), autoincrement=False, nullable=True))
    op.add_column('protocols', sa.Column('plain_text_private', sa.VARCHAR(), autoincrement=False, nullable=True))
    op.drop_column('protocols', 'content_public')
    op.drop_column('protocols', 'content_private')
    # ### end Alembic commands ###
