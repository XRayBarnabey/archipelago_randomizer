from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import (
    get_archipelago_service,
    get_db,
    get_draw_service,
    get_eligibility_service,
    get_steam_service,
)
from app.errors import NotFoundError
from app.models import (
    ArchipelagoGame,
    ArchipelagoSourceRecord,
    GameMapping,
    PlayerGameOwnership,
    SteamGame,
    SteamPlayer,
)
from app.schemas import (
    ArchipelagoGameOut,
    ArchipelagoGameUpdate,
    CommonGamesResponse,
    DrawHistoryItem,
    DrawResponse,
    EligibleGameOut,
    MappingCreate,
    MappingOut,
    MappingUpdate,
    OwnerOut,
    PlayerCreate,
    PlayerOut,
    SelectionRequest,
    SourceOut,
    SourceSyncResult,
    SyncResultOut,
)
from app.services.archipelago_service import ArchipelagoService
from app.services.draw_service import DrawService
from app.services.eligibility_service import EligibilityService, EligibleGame, Filters
from app.services.mapping_service import MappingService
from app.services.steam_service import SteamService

router = APIRouter()


def _steam_url(app_id: int) -> str:
    return f"https://store.steampowered.com/app/{app_id}/"


def _player_out(db: Session, player: SteamPlayer) -> PlayerOut:
    count = db.scalar(
        select(func.count()).select_from(PlayerGameOwnership).where(PlayerGameOwnership.player_id == player.id)
    )
    out = PlayerOut.model_validate(player)
    out.game_count = count or 0
    return out


def _eligible_out(e: EligibleGame, players_count: int, db: Session) -> EligibleGameOut:
    g = e.archipelago_game
    source = db.get(ArchipelagoSourceRecord, g.source_id) if g.source_id else None
    return EligibleGameOut(
        name=e.name,
        steam_app_id=e.steam_app_id,
        steam_url=_steam_url(e.steam_app_id),
        header_image_url=e.header_image_url,
        archipelago_game_id=g.id,
        archipelago_name=g.name,
        archipelago_slug=g.slug,
        archipelago_status=g.status,
        archipelago_detail_status=g.detail_status,
        source_name=source.name if source else None,
        mapping_id=e.mapping.id,
        mapping_type=e.mapping.mapping_type,
        mapping_verified=e.mapping.verified,
        owned_by_count=players_count,
        players_count=players_count,
    )


def _filters(f) -> Filters:
    return Filters(
        mode=f.mode,
        exclude_drawn=f.exclude_drawn,
        exclude_last_n=f.exclude_last_n,
        excluded_game_ids=f.excluded_game_ids,
    )


def _mapping_out(db: Session, m: GameMapping) -> MappingOut:
    out = MappingOut.model_validate(m)
    game = db.get(ArchipelagoGame, m.archipelago_game_id)
    out.archipelago_game_name = game.name if game else None
    out.steam_game_name = db.scalar(select(SteamGame.name).where(SteamGame.steam_app_id == m.steam_app_id))
    return out


@router.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(select(1))
    return {"status": "ok"}


# --- players ----------------------------------------------------------------
@router.get("/players", response_model=list[PlayerOut])
def list_players(db: Session = Depends(get_db)):
    counts = dict(
        db.execute(
            select(PlayerGameOwnership.player_id, func.count()).group_by(PlayerGameOwnership.player_id)
        ).all()
    )
    result = []
    for p in db.scalars(select(SteamPlayer).order_by(SteamPlayer.id)):
        out = PlayerOut.model_validate(p)
        out.game_count = counts.get(p.id, 0)
        result.append(out)
    return result


@router.post("/players", response_model=PlayerOut, status_code=201)
def add_player(body: PlayerCreate, service: SteamService = Depends(get_steam_service)):
    player = service.add_player(body.input)
    return _player_out(service.db, player)


@router.post("/players/sync", response_model=list[SyncResultOut])
def sync_all_players(force: bool = False, service: SteamService = Depends(get_steam_service)):
    return [SyncResultOut(**r.__dict__) for r in service.sync_all(force)]


@router.get("/players/{player_id}", response_model=PlayerOut)
def get_player(player_id: int, db: Session = Depends(get_db)):
    player = db.get(SteamPlayer, player_id)
    if player is None:
        raise NotFoundError("Joueur introuvable.")
    return _player_out(db, player)


@router.delete("/players/{player_id}", status_code=204)
def delete_player(player_id: int, db: Session = Depends(get_db)):
    player = db.get(SteamPlayer, player_id)
    if player is None:
        raise NotFoundError("Joueur introuvable.")
    db.delete(player)
    db.commit()
    return Response(status_code=204)


@router.post("/players/{player_id}/sync", response_model=SyncResultOut)
def sync_player(player_id: int, force: bool = False, service: SteamService = Depends(get_steam_service)):
    return SyncResultOut(**service.sync_player(player_id, force).__dict__)


# --- archipelago -----------------------------------------------------------
@router.get("/archipelago/games", response_model=list[ArchipelagoGameOut])
def list_archipelago_games(
    status: str | None = None,
    enabled: bool | None = None,
    unmapped: bool | None = None,
    q: str | None = Query(default=None, max_length=100),
    db: Session = Depends(get_db),
):
    stmt = select(ArchipelagoGame).options(selectinload(ArchipelagoGame.mappings), selectinload(ArchipelagoGame.source))
    if status:
        stmt = stmt.where(ArchipelagoGame.status == status)
    if enabled is not None:
        stmt = stmt.where(ArchipelagoGame.enabled.is_(enabled))
    if q:
        stmt = stmt.where(func.lower(ArchipelagoGame.name).contains(q.lower(), autoescape=True))
    result = []
    for g in db.scalars(stmt.order_by(func.lower(ArchipelagoGame.name))):
        if unmapped is not None and (not g.mappings) != unmapped:
            continue
        out = ArchipelagoGameOut.model_validate(g)
        out.source_name = g.source.name if g.source else None
        out.steam_app_ids = [m.steam_app_id for m in g.mappings]
        out.has_verified_mapping = any(m.verified for m in g.mappings)
        result.append(out)
    return result


@router.patch("/archipelago/games/{game_id}", response_model=ArchipelagoGameOut)
def update_archipelago_game(game_id: int, body: ArchipelagoGameUpdate, db: Session = Depends(get_db)):
    game = db.get(ArchipelagoGame, game_id)
    if game is None:
        raise NotFoundError("Jeu Archipelago introuvable.")
    game.enabled = body.enabled
    db.commit()
    out = ArchipelagoGameOut.model_validate(game)
    out.source_name = game.source.name if game.source else None
    out.steam_app_ids = [m.steam_app_id for m in game.mappings]
    out.has_verified_mapping = any(m.verified for m in game.mappings)
    return out


@router.get("/archipelago/sources", response_model=list[SourceOut])
def list_sources(service: ArchipelagoService = Depends(get_archipelago_service)):
    service.ensure_sources()
    return list(service.db.scalars(select(ArchipelagoSourceRecord).order_by(ArchipelagoSourceRecord.id)))


@router.post("/archipelago/sync", response_model=list[SourceSyncResult])
def sync_archipelago(service: ArchipelagoService = Depends(get_archipelago_service)):
    return service.sync()


# --- mappings --------------------------------------------------------------
@router.get("/mappings", response_model=list[MappingOut])
def list_mappings(verified: bool | None = None, db: Session = Depends(get_db)):
    return [_mapping_out(db, m) for m in MappingService(db).list(verified)]


@router.post("/mappings", response_model=MappingOut, status_code=201)
def create_mapping(body: MappingCreate, db: Session = Depends(get_db)):
    m = MappingService(db).create(**body.model_dump())
    return _mapping_out(db, m)


@router.post("/mappings/auto-match")
def auto_match(db: Session = Depends(get_db)):
    return {"created": MappingService(db).auto_match_by_name()}


@router.put("/mappings/{mapping_id}", response_model=MappingOut)
def update_mapping(mapping_id: int, body: MappingUpdate, db: Session = Depends(get_db)):
    m = MappingService(db).update(mapping_id, **body.model_dump(exclude_unset=True))
    return _mapping_out(db, m)


@router.delete("/mappings/{mapping_id}", status_code=204)
def delete_mapping(mapping_id: int, db: Session = Depends(get_db)):
    MappingService(db).delete(mapping_id)
    return Response(status_code=204)


# --- selection & draw ------------------------------------------------------
@router.post("/selection/common-games", response_model=CommonGamesResponse)
def common_games(
    body: SelectionRequest,
    service: EligibilityService = Depends(get_eligibility_service),
    db: Session = Depends(get_db),
):
    ids = list(dict.fromkeys(body.player_ids))
    games = service.get_eligible_games(ids, _filters(body.filters))
    return CommonGamesResponse(
        eligible_games_count=len(games),
        players_count=len(ids),
        games=[_eligible_out(g, len(ids), db) for g in games],
    )


@router.post("/draw", response_model=DrawResponse)
def draw(body: SelectionRequest, service: DrawService = Depends(get_draw_service), db: Session = Depends(get_db)):
    result, chosen, count, players = service.draw(body.player_ids, _filters(body.filters))
    return DrawResponse(
        draw_id=result.id,
        selected_game=_eligible_out(chosen, len(players), db),
        eligible_games_count=count,
        players_count=len(players),
        owners=[OwnerOut(id=p.id, display_name=p.display_name) for p in players],
    )


@router.get("/draws", response_model=list[DrawHistoryItem])
def draws(limit: int = Query(default=100, ge=1, le=500), service: DrawService = Depends(get_draw_service)):
    return [
        DrawHistoryItem(
            id=d.id,
            created_at=d.created_at,
            filters=d.filters or {},
            game_id=d.selected_game_id,
            archipelago_name=d.selected_game.name,
            archipelago_slug=d.selected_game.slug,
            steam_app_id=d.steam_app_id,
            steam_url=_steam_url(d.steam_app_id) if d.steam_app_id else None,
            players=[OwnerOut(id=p.player.id, display_name=p.player.display_name) for p in d.participants],
        )
        for d in service.history(limit)
    ]
