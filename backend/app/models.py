from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, utcnow


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class SteamPlayer(TimestampMixin, Base):
    __tablename__ = "steam_players"

    id: Mapped[int] = mapped_column(primary_key=True)
    steam_id: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    profile_url: Mapped[str | None] = mapped_column(String(512))
    display_name: Mapped[str] = mapped_column(String(255))
    avatar_url: Mapped[str | None] = mapped_column(String(512))
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # True once a valid library snapshot was stored. A failed sync never resets it.
    library_valid: Mapped[bool] = mapped_column(Boolean, default=False)
    last_sync_status: Mapped[str | None] = mapped_column(String(32))  # ok / private / error
    last_sync_error: Mapped[str | None] = mapped_column(Text)
    last_sync_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    ownerships: Mapped[list["PlayerGameOwnership"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True
    )
    draw_participations: Mapped[list["DrawParticipant"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True
    )


class SteamGame(TimestampMixin, Base):
    __tablename__ = "steam_games"

    id: Mapped[int] = mapped_column(primary_key=True)
    steam_app_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(512))
    header_image_url: Mapped[str | None] = mapped_column(String(512))


class PlayerGameOwnership(Base):
    __tablename__ = "player_game_ownership"
    __table_args__ = (UniqueConstraint("player_id", "game_id", name="uq_player_game"),)

    player_id: Mapped[int] = mapped_column(
        ForeignKey("steam_players.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    game_id: Mapped[int] = mapped_column(
        ForeignKey("steam_games.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ArchipelagoSourceRecord(Base):
    __tablename__ = "archipelago_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    url: Mapped[str] = mapped_column(String(512))
    type: Mapped[str] = mapped_column(String(32))  # html / mediawiki / json
    trust_level: Mapped[str] = mapped_column(String(16))  # official / community / unknown
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sync_status: Mapped[str | None] = mapped_column(String(16))
    last_error: Mapped[str | None] = mapped_column(Text)


class ArchipelagoGame(TimestampMixin, Base):
    __tablename__ = "archipelago_games"
    __table_args__ = (UniqueConstraint("source_id", "external_id", name="uq_ap_source_external"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="unknown")  # official / community / unknown
    detail_status: Mapped[str | None] = mapped_column(String(16))  # stable / unstable / untested / deprecated
    source_id: Mapped[int | None] = mapped_column(ForeignKey("archipelago_sources.id", ondelete="SET NULL"))
    external_id: Mapped[str | None] = mapped_column(String(255))
    version: Mapped[str | None] = mapped_column(String(64))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    source: Mapped[ArchipelagoSourceRecord | None] = relationship()
    mappings: Mapped[list["GameMapping"]] = relationship(cascade="all, delete-orphan", passive_deletes=True)
    seen_in: Mapped[list["ArchipelagoGameSource"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True
    )


class ArchipelagoGameSource(Base):
    """Every source that lists a (deduplicated) game."""

    __tablename__ = "archipelago_game_sources"

    game_id: Mapped[int] = mapped_column(ForeignKey("archipelago_games.id", ondelete="CASCADE"), primary_key=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("archipelago_sources.id", ondelete="CASCADE"), primary_key=True
    )
    external_id: Mapped[str | None] = mapped_column(String(255))


class GameMapping(TimestampMixin, Base):
    __tablename__ = "game_mappings"
    __table_args__ = (UniqueConstraint("archipelago_game_id", "steam_app_id", name="uq_mapping_pair"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    archipelago_game_id: Mapped[int] = mapped_column(
        ForeignKey("archipelago_games.id", ondelete="CASCADE"), index=True
    )
    steam_app_id: Mapped[int] = mapped_column(BigInteger, index=True)
    mapping_type: Mapped[str] = mapped_column(String(16))  # automatic / manual / imported / guessed
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)

    archipelago_game: Mapped[ArchipelagoGame] = relationship(back_populates="mappings")


class Draw(Base):
    __tablename__ = "draws"

    id: Mapped[int] = mapped_column(primary_key=True)
    selected_game_id: Mapped[int] = mapped_column(ForeignKey("archipelago_games.id", ondelete="CASCADE"))
    steam_app_id: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    filters: Mapped[dict] = mapped_column(JSON, default=dict)

    selected_game: Mapped[ArchipelagoGame] = relationship()
    participants: Mapped[list["DrawParticipant"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True
    )


class DrawParticipant(Base):
    __tablename__ = "draw_participants"

    draw_id: Mapped[int] = mapped_column(ForeignKey("draws.id", ondelete="CASCADE"), primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("steam_players.id", ondelete="CASCADE"), primary_key=True)

    player: Mapped[SteamPlayer] = relationship(back_populates="draw_participations")


Index("ix_draw_participants_player", DrawParticipant.player_id)
