from fastapi import APIRouter, Depends, File, Query, Request, Response, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import (
    get_auth_service,
    require_admin,
    get_archipelago_service,
    get_db,
    get_draw_service,
    get_eligibility_service,
    get_steam_service,
)
from app.config import get_settings
from app.db import utcnow
from app.errors import NotFoundError, ValidationFailed
from app.models import (
    AdminCredential,
    AppLogo,
    ArchipelagoGame,
    ArchipelagoSourceRecord,
    GameMapping,
    PlayerGameOwnership,
    SteamGame,
    SteamPlayer,
)
from app.schemas import (
    ClearHistoryOut,
    LoginRequest,
    PasswordChangeRequest,
    SessionOut,
    ArchipelagoGameOut,
    ArchipelagoGameUpdate,
    CommonGamesResponse,
    ArchipelagoStatusOut,
    DrawHistoryItem,
    DrawPerPlayerResponse,
    DrawPerPlayerResultsResponse,
    PerPlayerDrawResult,
    PlayerDrawOut,
    PlayerGamesEntry,
    PlayerGamesResponse,
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
from app.services.auth_service import AuthService
from app.services.draw_service import DrawService
from app.services.eligibility_service import EligibilityService, EligibleGame, Filters
from app.services.mapping_service import MappingService
from app.services.steam_service import SteamService

router = APIRouter()
admin_router = APIRouter(dependencies=[Depends(require_admin)])


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
        allow_duplicates=f.allow_duplicates,
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


@router.get("/players/search", response_model=list[PlayerOut])
def search_players(
    query: str = Query(min_length=1, max_length=100), service: SteamService = Depends(get_steam_service)
):
    return [_player_out(service.db, p) for p in service.search_players(query)]


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
@admin_router.get("/archipelago/games", response_model=list[ArchipelagoGameOut])
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


@admin_router.patch("/archipelago/games/{game_id}", response_model=ArchipelagoGameOut)
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


@admin_router.get("/archipelago/status", response_model=ArchipelagoStatusOut)
def archipelago_status(db: Session = Depends(get_db)):
    verified = GameMapping.verified.is_(True)
    return ArchipelagoStatusOut(
        sync_enabled=get_settings().archipelago_sync_enabled,
        games_count=db.scalar(select(func.count()).select_from(ArchipelagoGame)) or 0,
        enabled_games_count=db.scalar(
            select(func.count()).select_from(ArchipelagoGame).where(ArchipelagoGame.enabled.is_(True))
        )
        or 0,
        mappings_count=db.scalar(select(func.count()).select_from(GameMapping)) or 0,
        verified_mappings_count=db.scalar(select(func.count()).select_from(GameMapping).where(verified)) or 0,
        games_with_verified_mapping=db.scalar(
            select(func.count(func.distinct(GameMapping.archipelago_game_id))).where(verified)
        )
        or 0,
    )


@admin_router.get("/archipelago/sources", response_model=list[SourceOut])
def list_sources(service: ArchipelagoService = Depends(get_archipelago_service)):
    service.ensure_sources()
    return list(service.db.scalars(select(ArchipelagoSourceRecord).order_by(ArchipelagoSourceRecord.id)))


@admin_router.post("/archipelago/sync", response_model=list[SourceSyncResult])
def sync_archipelago(service: ArchipelagoService = Depends(get_archipelago_service)):
    return service.sync()


# --- mappings --------------------------------------------------------------
@admin_router.get("/mappings", response_model=list[MappingOut])
def list_mappings(verified: bool | None = None, db: Session = Depends(get_db)):
    return [_mapping_out(db, m) for m in MappingService(db).list(verified)]


@admin_router.post("/mappings", response_model=MappingOut, status_code=201)
def create_mapping(body: MappingCreate, db: Session = Depends(get_db)):
    m = MappingService(db).create(**body.model_dump())
    return _mapping_out(db, m)


@admin_router.post("/mappings/auto-match")
def auto_match(db: Session = Depends(get_db)):
    return {"created": MappingService(db).auto_match_by_name()}


@admin_router.put("/mappings/{mapping_id}", response_model=MappingOut)
def update_mapping(mapping_id: int, body: MappingUpdate, db: Session = Depends(get_db)):
    m = MappingService(db).update(mapping_id, **body.model_dump(exclude_unset=True))
    return _mapping_out(db, m)


@admin_router.delete("/mappings/{mapping_id}", status_code=204)
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


def _player_games(body: SelectionRequest, service: EligibilityService, db: Session):
    return service.get_games_per_player(body.player_ids, _filters(body.filters))


@router.post("/selection/player-games", response_model=PlayerGamesResponse)
def player_games(
    body: SelectionRequest,
    service: EligibilityService = Depends(get_eligibility_service),
    db: Session = Depends(get_db),
):
    players, per_player = _player_games(body, service, db)
    return PlayerGamesResponse(
        players_count=len(players),
        players={
            p.id: PlayerGamesEntry(
                player=OwnerOut(id=p.id, display_name=p.display_name),
                games_count=len(per_player[p.id]),
                games=[_eligible_out(g, 1, db) for g in per_player[p.id]],
            )
            for p in players
        },
    )


@router.post("/draw/from-player-games", response_model=DrawPerPlayerResponse)
def draw_from_player_games(
    body: SelectionRequest, service: DrawService = Depends(get_draw_service), db: Session = Depends(get_db)
):
    players, per_player, chosen = service.draw_per_player(body.player_ids, _filters(body.filters))
    return DrawPerPlayerResponse(
        players_count=len(players),
        allow_duplicates=body.filters.allow_duplicates,
        draws={
            p.id: PlayerDrawOut(
                player=OwnerOut(id=p.id, display_name=p.display_name),
                eligible_games_count=len(per_player[p.id]),
                selected_game=_eligible_out(chosen[p.id], 1, db),
            )
            for p in players
        },
    )


@router.post("/draw/per-player", response_model=DrawPerPlayerResultsResponse)
def draw_per_player(
    body: SelectionRequest, service: DrawService = Depends(get_draw_service), db: Session = Depends(get_db)
):
    players, per_player, chosen, draws = service.draw_per_player_and_record(
        body.player_ids, _filters(body.filters)
    )
    return DrawPerPlayerResultsResponse(
        players_count=len(players),
        eligible_games_count=sum(len(per_player[p.id]) for p in players),
        allow_duplicates=body.filters.allow_duplicates,
        results=[
            PerPlayerDrawResult(
                draw_id=draws[p.id].id,
                player=OwnerOut(id=p.id, display_name=p.display_name),
                eligible_games_count=len(per_player[p.id]),
                selected_game=_eligible_out(chosen[p.id], 1, db),
            )
            for p in players
        ],
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


@router.delete("/draws", response_model=ClearHistoryOut)
def clear_draws(service: DrawService = Depends(get_draw_service)):
    return ClearHistoryOut(deleted=service.clear_history())


# --- admin authentication ----------------------------------------------------
def _session_out(auth: AuthService, cred: AdminCredential, token: str | None = None, expires: int | None = None):
    return SessionOut(
        username=cred.username, default_credentials=auth.is_default(cred), token=token, expires_at=expires
    )


@router.post("/admin/login", response_model=SessionOut)
def admin_login(body: LoginRequest, request: Request, auth: AuthService = Depends(get_auth_service)):
    client_key = request.client.host if request.client else "unknown"
    token, expires, cred = auth.login(body.username, body.password, client_key)
    return _session_out(auth, cred, token, expires)


@router.post("/admin/logout", status_code=204)
def admin_logout(cred: AdminCredential = Depends(require_admin)):
    # tokens are stateless: the client discards its token; they expire or are invalidated by a password change
    return Response(status_code=204)


@router.get("/admin/session", response_model=SessionOut)
def admin_session(cred: AdminCredential = Depends(require_admin), auth: AuthService = Depends(get_auth_service)):
    return _session_out(auth, cred)


@router.post("/admin/password", response_model=SessionOut)
def admin_password(
    body: PasswordChangeRequest,
    cred: AdminCredential = Depends(require_admin),
    auth: AuthService = Depends(get_auth_service),
):
    if body.new_password != body.confirm_password:
        raise ValidationFailed("La confirmation ne correspond pas au nouveau mot de passe.")
    token, expires = auth.change_credentials(cred, body.current_password, body.new_password, body.new_username)
    return _session_out(auth, cred, token, expires)


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MAX_LOGO_BYTES = 2 * 1024 * 1024


@router.get("/logo")
def get_logo(db: Session = Depends(get_db)):
    logo = db.scalar(select(AppLogo))
    if logo is None:
        raise NotFoundError("Aucun logo n'est défini.")
    return Response(content=logo.data, media_type=logo.content_type, headers={"Cache-Control": "no-cache"})


@admin_router.post("/admin/logo", status_code=204)
async def upload_logo(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if (file.content_type or "").lower() != "image/png":
        raise ValidationFailed("Le logo doit être un fichier PNG.")
    data = await file.read(MAX_LOGO_BYTES + 1)
    if len(data) > MAX_LOGO_BYTES:
        raise ValidationFailed("Le logo ne doit pas dépasser 2 Mo.")
    if not data.startswith(PNG_SIGNATURE):
        raise ValidationFailed("Le fichier n'est pas un PNG valide.")
    logo = db.scalar(select(AppLogo))
    if logo is None:
        db.add(AppLogo(content_type="image/png", data=data))
    else:
        logo.data = data
        logo.updated_at = utcnow()
    db.commit()
    return Response(status_code=204)


@admin_router.delete("/admin/logo", status_code=204)
def delete_logo(db: Session = Depends(get_db)):
    logo = db.scalar(select(AppLogo))
    if logo is not None:
        db.delete(logo)
        db.commit()
    return Response(status_code=204)
