"""Add admin_id to halls

Revision ID: 0ea7aa1e7f0a
Revises: 9118fd36390c
Create Date: 2025-12-12 12:28:46.294632

"""
from alembic import op
import sqlalchemy as sa


revision = '0ea7aa1e7f0a'
down_revision = '9118fd36390c'
branch_labels = None
depends_on = None


def upgrade():
    # 1️⃣ Add column as nullable first
    op.add_column("halls", sa.Column("admin_id", sa.Integer(), nullable=True))

    # 2️⃣ Set default admin ID for existing halls (use admin ID = 1)
    op.execute("UPDATE halls SET admin_id = 1 WHERE admin_id IS NULL")

    # 3️⃣ Make column NOT NULL
    op.alter_column("halls", "admin_id", nullable=False)

    # 4️⃣ Add FK constraint
    op.create_foreign_key(
        "fk_halls_admin_id",
        "halls",
        "admins",
        ["admin_id"],
        ["id"],
        ondelete="CASCADE"
    )


def downgrade():
    op.drop_constraint("fk_halls_admin_id", "halls", type_="foreignkey")
    op.drop_column("halls", "admin_id")

