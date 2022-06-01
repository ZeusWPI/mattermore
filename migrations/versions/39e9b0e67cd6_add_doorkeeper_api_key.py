"""Add doorkeeper api key

Revision ID: 39e9b0e67cd6
Revises: f6aa31fc6bae
Create Date: 2022-05-25 19:57:21.796004

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "39e9b0e67cd6"
down_revision = "f6aa31fc6bae"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column("user", sa.Column("doorkey", sa.String(length=32), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("user", "doorkey")
    # ### end Alembic commands ###
