"""empty message

Revision ID: 279bfa293885
Revises: 0686095ee9dd
Create Date: 2017-05-06 21:28:13.577142

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Session = sessionmaker()

Base = declarative_base()

class ProtocolType(Base):
    __tablename__ = "protocoltypes"
    id = sa.Column(sa.Integer, primary_key=True)
    modify_group = sa.Column(sa.String)
    publish_group = sa.Column(sa.String)


# revision identifiers, used by Alembic.
revision = '279bfa293885'
down_revision = '0686095ee9dd'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('protocoltypes', sa.Column('publish_group', sa.String(), nullable=True))
    # ### end Alembic commands ###

    bind = op.get_bind()
    session = Session(bind=bind)
    for protocoltype in session.query(ProtocolType):
        protocoltype.publish_group = protocoltype.modify_group
    session.commit()


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('protocoltypes', 'publish_group')
    # ### end Alembic commands ###
