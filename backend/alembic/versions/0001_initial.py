"""initial schema

Revision ID: 0001
Revises:
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "steam_players",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("steam_id", sa.String(20), nullable=False),
        sa.Column("profile_url", sa.String(512)),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("avatar_url", sa.String(512)),
        sa.Column("last_synced_at", TS),
        sa.Column("library_valid", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("last_sync_status", sa.String(32)),
        sa.Column("last_sync_error", sa.Text),
        sa.Column("last_sync_attempt_at", TS),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
    )
    op.create_index("ix_steam_players_steam_id", "steam_players", ["steam_id"], unique=True)

    op.create_table(
        "steam_games",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("steam_app_id", sa.BigInteger, nullable=False),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("header_image_url", sa.String(512)),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
    )
    op.create_index("ix_steam_games_steam_app_id", "steam_games", ["steam_app_id"], unique=True)

    op.create_table(
        "player_game_ownership",
        sa.Column("player_id", sa.Integer, sa.ForeignKey("steam_players.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("game_id", sa.Integer, sa.ForeignKey("steam_games.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("last_seen_at", TS, nullable=False),
        sa.UniqueConstraint("player_id", "game_id", name="uq_player_game"),
    )
    op.create_index("ix_player_game_ownership_player_id", "player_game_ownership", ["player_id"])
    op.create_index("ix_player_game_ownership_game_id", "player_game_ownership", ["game_id"])

    op.create_table(
        "archipelago_sources",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(128), nullable=False, unique=True),
        sa.Column("url", sa.String(512), nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("trust_level", sa.String(16), nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("last_synced_at", TS),
        sa.Column("last_sync_status", sa.String(16)),
        sa.Column("last_error", sa.Text),
    )

    op.create_table(
        "archipelago_games",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("status", sa.String(16), nullable=False, server_default="unknown"),
        sa.Column("detail_status", sa.String(16)),
        sa.Column("source_id", sa.Integer, sa.ForeignKey("archipelago_sources.id", ondelete="SET NULL")),
        sa.Column("external_id", sa.String(255)),
        sa.Column("version", sa.String(64)),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("last_synced_at", TS),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
        sa.UniqueConstraint("source_id", "external_id", name="uq_ap_source_external"),
    )
    op.create_index("ix_archipelago_games_slug", "archipelago_games", ["slug"], unique=True)

    op.create_table(
        "archipelago_game_sources",
        sa.Column("game_id", sa.Integer, sa.ForeignKey("archipelago_games.id", ondelete="CASCADE"), primary_key=True),
        sa.Column(
            "source_id", sa.Integer, sa.ForeignKey("archipelago_sources.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("external_id", sa.String(255)),
    )

    op.create_table(
        "game_mappings",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("archipelago_game_id", sa.Integer, sa.ForeignKey("archipelago_games.id", ondelete="CASCADE"), nullable=False),
        sa.Column("steam_app_id", sa.BigInteger, nullable=False),
        sa.Column("mapping_type", sa.String(16), nullable=False),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("verified", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
        sa.UniqueConstraint("archipelago_game_id", "steam_app_id", name="uq_mapping_pair"),
    )
    op.create_index("ix_game_mappings_steam_app_id", "game_mappings", ["steam_app_id"])
    op.create_index("ix_game_mappings_archipelago_game_id", "game_mappings", ["archipelago_game_id"])

    op.create_table(
        "draws",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("selected_game_id", sa.Integer, sa.ForeignKey("archipelago_games.id", ondelete="CASCADE"), nullable=False),
        sa.Column("steam_app_id", sa.BigInteger),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("filters", sa.JSON, nullable=False),
    )
    op.create_index("ix_draws_created_at", "draws", ["created_at"])

    op.create_table(
        "draw_participants",
        sa.Column("draw_id", sa.Integer, sa.ForeignKey("draws.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("player_id", sa.Integer, sa.ForeignKey("steam_players.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_index("ix_draw_participants_player", "draw_participants", ["player_id"])


def downgrade() -> None:
    for table in (
        "draw_participants",
        "draws",
        "game_mappings",
        "archipelago_game_sources",
        "archipelago_games",
        "archipelago_sources",
        "player_game_ownership",
        "steam_games",
        "steam_players",
    ):
        op.drop_table(table)
