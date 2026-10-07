import asyncio
import logging
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import utcnow
from app.integrations.archipelago.base import STATUS_RANK, ArchipelagoGameData, ArchipelagoSource, SourceFetchError
from app.models import ArchipelagoGame, ArchipelagoGameSource, ArchipelagoSourceRecord
from app.normalize import slugify
from app.services.mapping_service import MappingService

logger = logging.getLogger(__name__)


def deduplicate(games: list[ArchipelagoGameData]) -> list[ArchipelagoGameData]:
    """Merge entries of one source that share a slug, keeping the most informative data."""
    merged: dict[str, ArchipelagoGameData] = {}
    for g in games:
        slug = slugify(g.name)
        if not slug:
            continue
        cur = merged.get(slug)
        if cur is None:
            merged[slug] = g
            continue
        if STATUS_RANK[g.status] > STATUS_RANK[cur.status]:
            cur.status = g.status
        cur.description = cur.description or g.description
        cur.detail_status = cur.detail_status or g.detail_status
        cur.version = cur.version or g.version
        cur.steam_app_id = cur.steam_app_id or g.steam_app_id
    return list(merged.values())


class ArchipelagoService:
    def __init__(self, db: Session, sources: list[ArchipelagoSource]):
        self.db = db
        self.sources = sources

    def ensure_sources(self) -> dict[str, ArchipelagoSourceRecord]:
        records = {r.name: r for r in self.db.scalars(select(ArchipelagoSourceRecord))}
        for src in self.sources:
            if src.name not in records:
                rec = ArchipelagoSourceRecord(
                    name=src.name, url=src.url, type=src.type, trust_level=src.trust_level, enabled=True
                )
                self.db.add(rec)
                records[src.name] = rec
        self.db.commit()
        return records

    def sync(self) -> list[dict]:
        records = self.ensure_sources()
        results = []
        ordered = sorted(self.sources, key=lambda s: -STATUS_RANK.get(s.trust_level, 0))
        for src in ordered:
            rec = records[src.name]
            if not rec.enabled:
                continue
            started = time.monotonic()
            try:
                fetched = asyncio.run(src.fetch_games())
                games = deduplicate(fetched)
                self._store(rec, games)
                rec.last_sync_status = "ok"
                rec.last_error = None
                rec.last_synced_at = utcnow()
                self.db.commit()
                logger.info(
                    "Archipelago source %r synced: %d games in %.2fs", src.name, len(games), time.monotonic() - started
                )
                results.append({"source": src.name, "status": "ok", "games_count": len(games), "error": None})
            except Exception as exc:  # one failing source must not stop the others
                self.db.rollback()
                rec = self.db.get(ArchipelagoSourceRecord, rec.id)
                rec.last_sync_status = "error"
                rec.last_error = (str(exc) if isinstance(exc, SourceFetchError) else "") or type(exc).__name__
                self.db.commit()
                logger.warning("Archipelago source %r failed: %s", src.name, type(exc).__name__)
                results.append({"source": src.name, "status": "error", "games_count": 0, "error": rec.last_error})
        MappingService(self.db).auto_match_by_name()
        return results

    def _store(self, rec: ArchipelagoSourceRecord, games: list[ArchipelagoGameData]) -> None:
        now = utcnow()
        mappings = MappingService(self.db)
        for data in games:
            slug = slugify(data.name)
            status = data.status if data.status in STATUS_RANK else "unknown"
            game = self.db.scalar(select(ArchipelagoGame).where(ArchipelagoGame.slug == slug))
            if game is None:
                game = ArchipelagoGame(
                    name=data.name,
                    slug=slug,
                    description=data.description,
                    status=status,
                    detail_status=data.detail_status,
                    source_id=rec.id,
                    external_id=data.external_id,
                    version=data.version,
                    enabled=True,
                )
                self.db.add(game)
                self.db.flush()
            else:
                if STATUS_RANK[status] > STATUS_RANK.get(game.status, 0):
                    game.status = status
                    game.source_id = rec.id
                    game.external_id = data.external_id
                if not game.description and data.description:
                    game.description = data.description
                if data.detail_status and (not game.detail_status or game.source_id == rec.id):
                    game.detail_status = data.detail_status
                if data.version:
                    game.version = data.version
            # `enabled` and manual mappings are never touched by a sync.
            game.last_synced_at = now
            link = self.db.get(ArchipelagoGameSource, (game.id, rec.id))
            if link is None:
                self.db.add(ArchipelagoGameSource(game_id=game.id, source_id=rec.id, external_id=data.external_id))
            if data.steam_app_id:
                mappings.apply_source_app_ids(game, data.steam_app_id)
                self.db.flush()
