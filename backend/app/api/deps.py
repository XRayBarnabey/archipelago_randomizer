from collections.abc import Iterator

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.integrations.archipelago.base import ArchipelagoSource
from app.integrations.archipelago.registry import default_sources
from app.integrations.steam.client import SteamClient
from app.models import AdminCredential
from app.services.archipelago_service import ArchipelagoService
from app.services.auth_service import AuthService
from app.services.draw_service import DrawService
from app.services.eligibility_service import EligibilityService
from app.services.steam_service import SteamService


def build_archipelago_sources() -> list[ArchipelagoSource]:
    return default_sources(get_settings())


def get_archipelago_sources() -> list[ArchipelagoSource]:
    return build_archipelago_sources()


def get_steam_client(settings: Settings = Depends(get_settings)) -> Iterator[SteamClient]:
    client = SteamClient(settings.steam_api_key, timeout=settings.http_timeout)
    try:
        yield client
    finally:
        client.close()


def get_steam_service(
    db: Session = Depends(get_db),
    client: SteamClient = Depends(get_steam_client),
    settings: Settings = Depends(get_settings),
) -> SteamService:
    return SteamService(db, client, settings)


def get_archipelago_service(
    db: Session = Depends(get_db), sources: list[ArchipelagoSource] = Depends(get_archipelago_sources)
) -> ArchipelagoService:
    return ArchipelagoService(db, sources)


def get_eligibility_service(db: Session = Depends(get_db)) -> EligibilityService:
    return EligibilityService(db)


def get_draw_service(
    db: Session = Depends(get_db), eligibility: EligibilityService = Depends(get_eligibility_service)
) -> DrawService:
    return DrawService(db, eligibility)


def get_auth_service(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> AuthService:
    return AuthService(db, settings)


def bearer_token(request: Request) -> str | None:
    header = request.headers.get("Authorization", "")
    scheme, _, value = header.partition(" ")
    return value.strip() if scheme.lower() == "bearer" and value.strip() else None


def require_admin(request: Request, auth: AuthService = Depends(get_auth_service)) -> AdminCredential:
    return auth.verify_token(bearer_token(request))
