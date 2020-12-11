"""Add keyvalue store

Revision ID: eb812588d982
Revises: 49d24a3cb696
Create Date: 2020-12-11 01:51:57.007519

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'eb812588d982'
down_revision = '49d24a3cb696'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('key_value',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('keyname', sa.String(), nullable=False),
    sa.Column('value', sa.String(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('keyname')
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('key_value')
    # ### end Alembic commands ###
