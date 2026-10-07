import logging
import random

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.errors import AppError
from app.models import Draw, DrawParticipant
from app.services.eligibility_service import EligibilityService, EligibleGame, Filters

logger = logging.getLogger(__name__)
_rng = random.SystemRandom()


class NoCommonGames(AppError):
    status_code = 409
    code = "NO_COMMON_GAMES"


class NoCompatibleGames(AppError):
    status_code = 409
    code = "NO_COMPATIBLE_GAMES"


class DuplicatesUnavoidable(AppError):
    status_code = 409
    code = "DUPLICATES_UNAVOIDABLE"


def assign_distinct(candidates: dict[int, list[EligibleGame]]) -> dict[int, EligibleGame] | None:
    """Random assignment of one game per player with distinct archipelago games (bipartite matching)."""
    options = {pid: _rng.sample(games, len(games)) for pid, games in candidates.items()}
    owner: dict[int, int] = {}  # archipelago_game_id -> player_id
    chosen: dict[int, EligibleGame] = {}

    def place(pid: int, seen: set[int]) -> bool:
        for g in options[pid]:
            gid = g.archipelago_game.id
            if gid in seen:
                continue
            seen.add(gid)
            if gid not in owner or place(owner[gid], seen):
                owner[gid] = pid
                chosen[pid] = g
                return True
        return False

    pids = list(options)
    _rng.shuffle(pids)
    for pid in pids:
        if not place(pid, set()):
            return None
    return chosen


class DrawService:
    def __init__(self, db: Session, eligibility: EligibilityService):
        self.db = db
        self.eligibility = eligibility

    def draw(self, player_ids: list[int], filters: Filters) -> tuple[Draw, EligibleGame, int, list]:
        players = self.eligibility.validate_players(player_ids)
        eligible = self.eligibility.get_eligible_games([p.id for p in players], filters)
        if not eligible:
            raise NoCommonGames("Aucun jeu compatible Archipelago n'est possédé par tous les joueurs sélectionnés.")
        chosen = _rng.choice(eligible)
        draw = Draw(
            selected_game_id=chosen.archipelago_game.id,
            steam_app_id=chosen.steam_app_id,
            filters=filters.to_json(),
            participants=[DrawParticipant(player_id=p.id) for p in players],
        )
        self.db.add(draw)
        self.db.commit()
        logger.info(
            "Draw id=%s game=%r players=%d eligible=%d", draw.id, chosen.archipelago_game.name, len(players), len(eligible)
        )
        return draw, chosen, len(eligible), players

    def draw_per_player(self, player_ids: list[int], filters: Filters):
        players, per_player = self.eligibility.get_games_per_player(player_ids, filters)
        empty = [p.display_name for p in players if not per_player[p.id]]
        if empty:
            raise NoCompatibleGames(
                "Aucun jeu compatible Archipelago pour : " + ", ".join(empty) + "."
            )
        if filters.allow_duplicates:
            chosen = {p.id: _rng.choice(per_player[p.id]) for p in players}
        else:
            chosen = assign_distinct(per_player)
            if chosen is None:
                raise DuplicatesUnavoidable(
                    "Impossible d'attribuer un jeu différent à chaque joueur avec les jeux compatibles disponibles."
                )
        logger.info("Per-player draw players=%d", len(players))
        return players, per_player, chosen

    def draw_per_player_and_record(self, player_ids: list[int], filters: Filters):
        players, per_player, chosen = self.draw_per_player(player_ids, filters)
        draws = {}
        for player in players:
            game = chosen[player.id]
            draw = Draw(
                selected_game_id=game.archipelago_game.id,
                steam_app_id=game.steam_app_id,
                filters=filters.to_json(),
                participants=[DrawParticipant(player_id=player.id)],
            )
            self.db.add(draw)
            draws[player.id] = draw
        self.db.commit()
        return players, per_player, chosen, draws

    def history(self, limit: int = 100) -> list[Draw]:
        stmt = (
            select(Draw)
            .options(selectinload(Draw.selected_game), selectinload(Draw.participants).selectinload(DrawParticipant.player))
            .order_by(Draw.id.desc())
            .limit(limit)
        )
        return list(self.db.scalars(stmt))
