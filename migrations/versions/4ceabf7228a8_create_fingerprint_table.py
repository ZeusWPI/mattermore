"""create fingerprint table

Revision ID: 4ceabf7228a8
Revises: 39e9b0e67cd6
Create Date: 2022-06-01 17:42:42.456067

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "4ceabf7228a8"
down_revision = "39e9b0e67cd6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "fingerprint",
        sa.Column("id", sa.Integer(), nullable=False, unique=True, primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("note", sa.String(length=32), nullable=False),
        sa.Column("created_on", sa.Date(), nullable=False),
    )


def downgrade():
    op.drop_table("fingerprint")
