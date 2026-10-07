from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import PlayerGameOwnership, SteamGame, SteamPlayer


@dataclass(frozen=True)
class CommonGame:
    steam_app_id: int
    name: str
    header_image_url: str | None


class GameOwnershipProvider(Protocol):
    """Platform-agnostic ownership. Add other platforms by implementing this protocol."""

    platform: str

    def missing_libraries(self, player_ids: list[int]) -> list[SteamPlayer]: ...

    def common_games(self, player_ids: list[int]) -> list[CommonGame]: ...


class SteamOwnershipProvider:
    platform = "steam"

    def __init__(self, db: Session):
        self.db = db

    def missing_libraries(self, player_ids: list[int]) -> list[SteamPlayer]:
        return list(
            self.db.scalars(
                select(SteamPlayer).where(SteamPlayer.id.in_(player_ids), SteamPlayer.library_valid.is_(False))
            )
        )

    def common_games(self, player_ids: list[int]) -> list[CommonGame]:
        # Single SQL intersection: games owned by every selected player.
        stmt = (
            select(SteamGame.steam_app_id, SteamGame.name, SteamGame.header_image_url)
            .join(PlayerGameOwnership, PlayerGameOwnership.game_id == SteamGame.id)
            .where(PlayerGameOwnership.player_id.in_(player_ids))
            .group_by(SteamGame.id)
            .having(func.count(func.distinct(PlayerGameOwnership.player_id)) == len(player_ids))
        )
        return [CommonGame(*row) for row in self.db.execute(stmt)]
