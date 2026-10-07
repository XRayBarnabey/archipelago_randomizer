from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import AppError, NotFoundError, ValidationFailed
from app.models import ArchipelagoGame, Draw, GameMapping, SteamPlayer
from app.services.ownership import GameOwnershipProvider, SteamOwnershipProvider

MAX_PLAYERS = 8
MIN_PLAYERS = 1
RELIABLE_DETAIL = {"stable"}
EXCLUDED_DETAIL_OFFICIAL = {"deprecated"}
CHUNK = 500


@dataclass
class Filters:
    mode: Literal["official", "recommended", "extended"] = "recommended"
    exclude_drawn: bool = False
    exclude_last_n: int | None = None
    excluded_game_ids: list[int] = field(default_factory=list)

    def to_json(self) -> dict:
        return {
            "mode": self.mode,
            "exclude_drawn": self.exclude_drawn,
            "exclude_last_n": self.exclude_last_n,
            "excluded_game_ids": list(self.excluded_game_ids),
        }


@dataclass
class EligibleGame:
    archipelago_game: ArchipelagoGame
    mapping: GameMapping
    steam_app_id: int
    name: str
    header_image_url: str | None


def status_allowed(game: ArchipelagoGame, mode: str) -> bool:
    if mode == "extended":
        return True
    if game.status == "official":
        return game.detail_status not in EXCLUDED_DETAIL_OFFICIAL
    if mode == "official":
        return False
    return game.status == "community" and game.detail_status in RELIABLE_DETAIL


class EligibilityService:
    def __init__(self, db: Session, ownership: GameOwnershipProvider | None = None):
        self.db = db
        self.ownership = ownership or SteamOwnershipProvider(db)

    def validate_players(self, player_ids: list[int]) -> list[SteamPlayer]:
        ids = list(dict.fromkeys(player_ids))
        if not (MIN_PLAYERS <= len(ids) <= MAX_PLAYERS):
            raise ValidationFailed(
                f"Il faut sélectionner entre {MIN_PLAYERS} et {MAX_PLAYERS} joueurs.", code="INVALID_PLAYER_COUNT"
            )
        players = list(self.db.scalars(select(SteamPlayer).where(SteamPlayer.id.in_(ids)).order_by(SteamPlayer.id)))
        if len(players) != len(ids):
            raise NotFoundError("Un ou plusieurs joueurs sélectionnés n'existent pas.", code="PLAYER_NOT_FOUND")
        missing = self.ownership.missing_libraries(ids)
        if missing:
            names = ", ".join(p.display_name for p in missing)
            raise AppError(
                f"Aucune bibliothèque valide pour : {names}. Synchronisez ces joueurs "
                "(profil ou bibliothèque privé ?) avant de calculer l'intersection.",
                code="LIBRARY_UNAVAILABLE",
                status_code=409,
            )
        return players

    def get_eligible_games(self, player_ids: list[int], filters: Filters | None = None) -> list[EligibleGame]:
        filters = filters or Filters()
        players = self.validate_players(player_ids)
        ids = [p.id for p in players]
        common = {g.steam_app_id: g for g in self.ownership.common_games(ids)}
        if not common:
            return []

        excluded = set(filters.excluded_game_ids)
        if filters.exclude_drawn:
            excluded |= set(self.db.scalars(select(Draw.selected_game_id)))
        elif filters.exclude_last_n:
            recent = self.db.scalars(select(Draw.selected_game_id).order_by(Draw.id.desc()).limit(filters.exclude_last_n))
            excluded |= set(recent)

        app_ids = list(common)
        by_game: dict[int, EligibleGame] = {}
        for i in range(0, len(app_ids), CHUNK):
            stmt = (
                select(GameMapping, ArchipelagoGame)
                .join(ArchipelagoGame, ArchipelagoGame.id == GameMapping.archipelago_game_id)
                .where(
                    GameMapping.steam_app_id.in_(app_ids[i : i + CHUNK]),
                    GameMapping.verified.is_(True),
                    ArchipelagoGame.enabled.is_(True),
                )
                .order_by(GameMapping.confidence.desc(), GameMapping.steam_app_id)
            )
            for mapping, game in self.db.execute(stmt):
                if game.id in excluded or game.id in by_game or not status_allowed(game, filters.mode):
                    continue
                cg = common[mapping.steam_app_id]
                by_game[game.id] = EligibleGame(game, mapping, cg.steam_app_id, cg.name, cg.header_image_url)
        return sorted(by_game.values(), key=lambda e: e.archipelago_game.name.lower())
