"""Add mattermost user id

Revision ID: f6aa31fc6bae
Revises: eb812588d982
Create Date: 2021-06-17 01:55:42.493528

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f6aa31fc6bae"
down_revision = "eb812588d982"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column("user", sa.Column("mattermost_id", sa.String(255), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("user", "mattermost_id")
    # ### end Alembic commands ###
