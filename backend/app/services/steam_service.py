import logging
import time
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import as_utc, utcnow
from app.errors import ConflictError, NotFoundError, ValidationFailed
from app.integrations.steam.client import SteamClient
from app.integrations.steam.errors import (
    InvalidSteamInput,
    SteamError,
    SteamLibraryPrivate,
    SteamNotConfigured,
    SteamPlayerNotFound,
)
from app.integrations.steam.ids import parse_steam_input
from app.models import PlayerGameOwnership, SteamGame, SteamPlayer

logger = logging.getLogger(__name__)
CHUNK = 500


@dataclass
class SyncResult:
    player_id: int
    status: str  # ok / cached / private / error
    games_count: int | None = None
    error_code: str | None = None
    message: str | None = None


def _chunks(items: list, size: int = CHUNK):
    for i in range(0, len(items), size):
        yield items[i : i + size]


class SteamService:
    def __init__(self, db: Session, client: SteamClient, settings: Settings):
        self.db = db
        self.client = client
        self.settings = settings

    # --- players -------------------------------------------------------
    def add_player(self, raw_input: str) -> SteamPlayer:
        try:
            parsed = parse_steam_input(raw_input)
            steam_id = parsed.steam_id or self.client.resolve_vanity(parsed.vanity or "")
            profile = self.client.get_profile(steam_id)
        except InvalidSteamInput as exc:
            raise ValidationFailed(str(exc) or "Entrée invalide.", code=exc.code) from None
        except SteamPlayerNotFound as exc:
            raise NotFoundError(str(exc), code=exc.code) from None
        except SteamNotConfigured as exc:
            raise _steam_http_error(exc, 503)
        except SteamError as exc:
            raise _steam_http_error(exc, 502)

        if self.db.scalar(select(SteamPlayer.id).where(SteamPlayer.steam_id == profile.steam_id)):
            raise ConflictError("Ce joueur Steam existe déjà.", code="PLAYER_EXISTS")
        player = SteamPlayer(
            steam_id=profile.steam_id,
            profile_url=profile.profile_url,
            display_name=profile.display_name,
            avatar_url=profile.avatar_url,
            library_valid=False,
        )
        self.db.add(player)
        self.db.commit()
        logger.info("Added Steam player id=%s steam_id=%s", player.id, player.steam_id)
        return player

    # --- sync ----------------------------------------------------------
    def sync_player(self, player_id: int, force: bool = False) -> SyncResult:
        player = self.db.get(SteamPlayer, player_id)
        if player is None:
            raise NotFoundError("Joueur introuvable.")
        if not force and self._is_fresh(player):
            return SyncResult(player.id, "cached", self._count(player.id))

        started = time.monotonic()
        player.last_sync_attempt_at = utcnow()
        try:
            profile = self.client.get_profile(player.steam_id)
            player.display_name = profile.display_name
            player.avatar_url = profile.avatar_url or player.avatar_url
            player.profile_url = profile.profile_url or player.profile_url
            games = self.client.get_owned_games(player.steam_id)
            self._store_library(player, games)
            player.library_valid = True
            player.last_synced_at = utcnow()
            player.last_sync_status = "ok"
            player.last_sync_error = None
            self.db.commit()
            logger.info(
                "Steam sync ok player=%s games=%d duration=%.2fs",
                player.id,
                len(games),
                time.monotonic() - started,
            )
            return SyncResult(player.id, "ok", len(games))
        except SteamError as exc:
            self.db.rollback()
            player = self.db.get(SteamPlayer, player_id)
            status = "private" if isinstance(exc, SteamLibraryPrivate) else "error"
            message = str(exc) or exc.code
            player.last_sync_status = status
            player.last_sync_error = message
            player.last_sync_attempt_at = utcnow()
            self.db.commit()
            logger.warning("Steam sync failed player=%s status=%s code=%s", player.id, status, exc.code)
            return SyncResult(player.id, status, self._count(player.id), exc.code, message)

    def sync_all(self, force: bool = False) -> list[SyncResult]:
        ids = list(self.db.scalars(select(SteamPlayer.id).order_by(SteamPlayer.id)))
        return [self.sync_player(pid, force) for pid in ids]

    def _is_fresh(self, player: SteamPlayer) -> bool:
        last = as_utc(player.last_synced_at)
        if not player.library_valid or last is None or player.last_sync_status != "ok":
            return False
        return utcnow() - last < timedelta(seconds=self.settings.steam_cache_duration)

    def _count(self, player_id: int) -> int:
        return self.db.scalar(
            select(func.count()).select_from(PlayerGameOwnership).where(PlayerGameOwnership.player_id == player_id)
        ) or 0

    def _store_library(self, player: SteamPlayer, games) -> None:
        by_app = {g.app_id: g for g in games}
        app_ids = list(by_app)
        existing: dict[int, SteamGame] = {}
        for chunk in _chunks(app_ids):
            for sg in self.db.scalars(select(SteamGame).where(SteamGame.steam_app_id.in_(chunk))):
                existing[sg.steam_app_id] = sg
        new_rows = []
        for app_id, g in by_app.items():
            sg = existing.get(app_id)
            if sg is None:
                sg = SteamGame(steam_app_id=app_id, name=g.name, header_image_url=g.header_image_url)
                new_rows.append(sg)
                existing[app_id] = sg
            elif sg.name != g.name:
                sg.name = g.name
        self.db.add_all(new_rows)
        self.db.flush()

        wanted_ids = {sg.id for sg in existing.values()}
        current_ids = set(
            self.db.scalars(select(PlayerGameOwnership.game_id).where(PlayerGameOwnership.player_id == player.id))
        )
        for chunk in _chunks(list(current_ids - wanted_ids)):
            self.db.execute(
                delete(PlayerGameOwnership).where(
                    PlayerGameOwnership.player_id == player.id, PlayerGameOwnership.game_id.in_(chunk)
                )
            )
        now = utcnow()
        to_add = [
            {"player_id": player.id, "game_id": gid, "last_seen_at": now} for gid in wanted_ids - current_ids
        ]
        if to_add:
            self.db.execute(insert(PlayerGameOwnership), to_add)
        self.db.execute(
            update(PlayerGameOwnership).where(PlayerGameOwnership.player_id == player.id).values(last_seen_at=now)
        )


def _steam_http_error(exc: SteamError, status: int):
    from app.errors import AppError

    return AppError(str(exc) or exc.code, code=exc.code, status_code=status)
