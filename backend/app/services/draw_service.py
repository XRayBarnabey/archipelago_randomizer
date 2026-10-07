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

    def history(self, limit: int = 100) -> list[Draw]:
        stmt = (
            select(Draw)
            .options(selectinload(Draw.selected_game), selectinload(Draw.participants).selectinload(DrawParticipant.player))
            .order_by(Draw.id.desc())
            .limit(limit)
        )
        return list(self.db.scalars(stmt))
