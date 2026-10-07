"""application logo (PNG stored in database)

Revision ID: 0003
Revises: 0002
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_logo",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("content_type", sa.String(64), nullable=False),
        sa.Column("data", sa.LargeBinary, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("app_logo")
