import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import ConflictError, NotFoundError
from app.models import ArchipelagoGame, GameMapping, SteamGame
from app.normalize import normalize_name

logger = logging.getLogger(__name__)

MAPPING_TYPES = {"automatic", "manual", "imported", "guessed"}


class MappingService:
    def __init__(self, db: Session):
        self.db = db

    def list(self, verified: bool | None = None) -> list[GameMapping]:
        stmt = select(GameMapping).order_by(GameMapping.id)
        if verified is not None:
            stmt = stmt.where(GameMapping.verified.is_(verified))
        return list(self.db.scalars(stmt))

    def get(self, mapping_id: int) -> GameMapping:
        mapping = self.db.get(GameMapping, mapping_id)
        if mapping is None:
            raise NotFoundError("Mapping introuvable.")
        return mapping

    def create(
        self,
        archipelago_game_id: int,
        steam_app_id: int,
        mapping_type: str = "manual",
        confidence: float = 1.0,
        verified: bool = True,
    ) -> GameMapping:
        if self.db.get(ArchipelagoGame, archipelago_game_id) is None:
            raise NotFoundError("Jeu Archipelago introuvable.")
        exists = self.db.scalar(
            select(GameMapping.id).where(
                GameMapping.archipelago_game_id == archipelago_game_id,
                GameMapping.steam_app_id == steam_app_id,
            )
        )
        if exists:
            raise ConflictError("Ce mapping existe déjà.", code="MAPPING_EXISTS")
        mapping = GameMapping(
            archipelago_game_id=archipelago_game_id,
            steam_app_id=steam_app_id,
            mapping_type=mapping_type,
            confidence=confidence,
            verified=verified,
        )
        self.db.add(mapping)
        self.db.commit()
        return mapping

    def update(self, mapping_id: int, **changes) -> GameMapping:
        mapping = self.get(mapping_id)
        new_app = changes.get("steam_app_id")
        if new_app is not None and new_app != mapping.steam_app_id:
            clash = self.db.scalar(
                select(GameMapping.id).where(
                    GameMapping.archipelago_game_id == mapping.archipelago_game_id,
                    GameMapping.steam_app_id == new_app,
                )
            )
            if clash:
                raise ConflictError("Ce mapping existe déjà.", code="MAPPING_EXISTS")
        app_changed = new_app is not None and new_app != mapping.steam_app_id
        for key, value in changes.items():
            if value is not None:
                setattr(mapping, key, value)
        if app_changed and "mapping_type" not in changes:
            mapping.mapping_type = "manual"
        self.db.commit()
        return mapping

    def delete(self, mapping_id: int) -> None:
        self.db.delete(self.get(mapping_id))
        self.db.commit()

    def apply_source_app_ids(self, game: ArchipelagoGame, steam_app_id: int) -> None:
        """Explicit Steam App ID provided by a source: highest priority automatic mapping."""
        exists = self.db.scalar(
            select(GameMapping.id).where(
                GameMapping.archipelago_game_id == game.id, GameMapping.steam_app_id == steam_app_id
            )
        )
        if not exists:
            self.db.add(
                GameMapping(
                    archipelago_game_id=game.id,
                    steam_app_id=steam_app_id,
                    mapping_type="imported",
                    confidence=1.0,
                    verified=True,
                )
            )

    def auto_match_by_name(self) -> int:
        """Last-resort matching on normalized names. Results are always unverified guesses.

        Games that already have any mapping (manual or otherwise) are left untouched.
        """
        mapped_ids = set(self.db.scalars(select(GameMapping.archipelago_game_id).distinct()))
        games = [g for g in self.db.scalars(select(ArchipelagoGame)) if g.id not in mapped_ids]
        if not games:
            return 0
        wanted = {normalize_name(g.name) for g in games}
        steam_by_norm: dict[str, list[int]] = {}
        for app_id, name in self.db.execute(select(SteamGame.steam_app_id, SteamGame.name)):
            norm = normalize_name(name)
            if norm in wanted:
                steam_by_norm.setdefault(norm, []).append(app_id)
        created = 0
        for game in games:
            candidates = steam_by_norm.get(normalize_name(game.name), [])
            confidence = 0.6 if len(candidates) == 1 else 0.3
            for app_id in candidates:
                self.db.add(
                    GameMapping(
                        archipelago_game_id=game.id,
                        steam_app_id=app_id,
                        mapping_type="guessed",
                        confidence=confidence,
                        verified=False,
                    )
                )
                created += 1
        self.db.commit()
        logger.info("Name auto-matching created %d unverified mappings", created)
        return created

    def count(self) -> int:
        return self.db.scalar(select(func.count()).select_from(GameMapping)) or 0
