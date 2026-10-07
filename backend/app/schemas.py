from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Mode = Literal["official", "recommended", "extended"]
MappingType = Literal["automatic", "manual", "imported", "guessed"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class PlayerCreate(BaseModel):
    input: str = Field(min_length=1, max_length=512, description="SteamID64, profile URL or vanity name")


class PlayerOut(ORM):
    id: int
    steam_id: str
    profile_url: str | None
    display_name: str
    avatar_url: str | None
    last_synced_at: datetime | None
    library_valid: bool
    last_sync_status: str | None
    last_sync_error: str | None
    game_count: int = 0


class SyncResultOut(BaseModel):
    player_id: int
    status: str
    games_count: int | None = None
    error_code: str | None = None
    message: str | None = None


class SourceOut(ORM):
    id: int
    name: str
    url: str
    type: str
    trust_level: str
    enabled: bool
    last_synced_at: datetime | None
    last_sync_status: str | None
    last_error: str | None


class SourceSyncResult(BaseModel):
    source: str
    status: str
    games_count: int
    error: str | None = None


class MappingOut(ORM):
    id: int
    archipelago_game_id: int
    steam_app_id: int
    mapping_type: str
    confidence: float
    verified: bool
    archipelago_game_name: str | None = None
    steam_game_name: str | None = None


class MappingCreate(BaseModel):
    archipelago_game_id: int
    steam_app_id: int = Field(gt=0)
    mapping_type: MappingType = "manual"
    confidence: float = Field(default=1.0, ge=0, le=1)
    verified: bool = True


class MappingUpdate(BaseModel):
    steam_app_id: int | None = Field(default=None, gt=0)
    mapping_type: MappingType | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    verified: bool | None = None


class ArchipelagoGameOut(ORM):
    id: int
    name: str
    slug: str
    description: str | None
    status: str
    detail_status: str | None
    source_id: int | None
    source_name: str | None = None
    external_id: str | None
    version: str | None
    enabled: bool
    last_synced_at: datetime | None
    steam_app_ids: list[int] = []
    has_verified_mapping: bool = False


class ArchipelagoGameUpdate(BaseModel):
    enabled: bool


class FiltersIn(BaseModel):
    mode: Mode = "recommended"
    exclude_drawn: bool = False
    exclude_last_n: int | None = Field(default=None, ge=1, le=1000)
    excluded_game_ids: list[int] = Field(default_factory=list, max_length=5000)
    allow_duplicates: bool = False


class SelectionRequest(BaseModel):
    player_ids: list[int] = Field(min_length=1, max_length=50)
    filters: FiltersIn = Field(default_factory=FiltersIn)


class OwnerOut(BaseModel):
    id: int
    display_name: str


class EligibleGameOut(BaseModel):
    name: str
    steam_app_id: int
    steam_url: str
    header_image_url: str | None
    archipelago_game_id: int
    archipelago_name: str
    archipelago_slug: str
    archipelago_status: str
    archipelago_detail_status: str | None
    source_name: str | None
    mapping_id: int
    mapping_type: str
    mapping_verified: bool
    owned_by_count: int
    players_count: int


class CommonGamesResponse(BaseModel):
    eligible_games_count: int
    players_count: int
    games: list[EligibleGameOut]


class PlayerGamesEntry(BaseModel):
    player: OwnerOut
    games_count: int
    games: list[EligibleGameOut]


class PlayerGamesResponse(BaseModel):
    players_count: int
    players: dict[int, PlayerGamesEntry]


class PlayerDrawOut(BaseModel):
    player: OwnerOut
    eligible_games_count: int
    selected_game: EligibleGameOut


class DrawPerPlayerResponse(BaseModel):
    players_count: int
    allow_duplicates: bool
    draws: dict[int, PlayerDrawOut]


class PerPlayerDrawResult(BaseModel):
    draw_id: int
    player: OwnerOut
    eligible_games_count: int
    selected_game: EligibleGameOut


class DrawPerPlayerResultsResponse(BaseModel):
    players_count: int
    eligible_games_count: int
    allow_duplicates: bool
    results: list[PerPlayerDrawResult]


class ArchipelagoStatusOut(BaseModel):
    sync_enabled: bool
    games_count: int
    enabled_games_count: int
    mappings_count: int
    verified_mappings_count: int
    games_with_verified_mapping: int


class DrawResponse(BaseModel):
    draw_id: int
    selected_game: EligibleGameOut
    eligible_games_count: int
    players_count: int
    owners: list[OwnerOut]


class DrawHistoryItem(BaseModel):
    id: int
    created_at: datetime
    filters: dict
    game_id: int
    archipelago_name: str
    archipelago_slug: str
    steam_app_id: int | None
    steam_url: str | None
    players: list[OwnerOut]
