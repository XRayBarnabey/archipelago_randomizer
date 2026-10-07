"""admin credentials (salted hash, seeded with admin/admin)

Revision ID: 0002
Revises: 0001
"""
import secrets
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

from app.services.auth_service import DEFAULT_PASSWORD, DEFAULT_USERNAME, hash_password

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    table = op.create_table(
        "admin_credentials",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("secret_key", sa.String(128), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.bulk_insert(
        table,
        [
            {
                "username": DEFAULT_USERNAME,
                "password_hash": hash_password(DEFAULT_PASSWORD),
                "secret_key": secrets.token_hex(32),
                "updated_at": datetime.now(timezone.utc),
            }
        ],
    )


def downgrade() -> None:
    op.drop_table("admin_credentials")
