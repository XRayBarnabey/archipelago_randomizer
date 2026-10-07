import os

os.environ.setdefault("ENVIRONMENT", "test")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_archipelago_sources, get_steam_client
from app.config import Settings, get_settings
from app.db import Base, get_db, make_engine
from app.integrations.steam.client import SteamOwnedGame, SteamProfile
from app.integrations.steam.errors import SteamPlayerNotFound
from app.main import create_app
from app.models import (
    ArchipelagoGame,
    GameMapping,
    PlayerGameOwnership,
    SteamGame,
    SteamPlayer,
)


class FakeSteamClient:
    """In-memory replacement for SteamClient. Set `error` to make calls fail."""

    def __init__(self):
        self.profiles: dict[str, str] = {}
        self.libraries: dict[str, list[SteamOwnedGame] | Exception] = {}
        self.vanities: dict[str, str] = {}
        self.error: Exception | None = None
        self.calls = 0

    def resolve_vanity(self, vanity):
        if vanity not in self.vanities:
            raise SteamPlayerNotFound("nope")
        return self.vanities[vanity]

    def get_profile(self, steam_id):
        if self.error:
            raise self.error
        if steam_id not in self.profiles:
            raise SteamPlayerNotFound("nope")
        return SteamProfile(steam_id, self.profiles[steam_id], f"https://steamcommunity.com/profiles/{steam_id}", None, True)

    def get_owned_games(self, steam_id):
        self.calls += 1
        if self.error:
            raise self.error
        lib = self.libraries.get(steam_id, [])
        if isinstance(lib, Exception):
            raise lib
        return lib

    def close(self):
        pass


def game(app_id, name=None):
    return SteamOwnedGame(app_id, name or f"Game {app_id}", f"https://img/{app_id}.jpg")


@pytest.fixture
def engine():
    eng = make_engine("sqlite://")
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine):
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        yield session


@pytest.fixture
def settings():
    return Settings(steam_api_key="test-key", steam_cache_duration=3600, admin_login_delay=0)


@pytest.fixture
def steam():
    return FakeSteamClient()


@pytest.fixture
def api_sources():
    return []


@pytest.fixture(autouse=True)
def _reset_throttle():
    from app.services.auth_service import throttle

    throttle._failures.clear()


@pytest.fixture
def client(engine, steam, api_sources, settings):
    app = create_app()
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def _db():
        with factory() as s:
            yield s

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_steam_client] = lambda: steam
    app.dependency_overrides[get_archipelago_sources] = lambda: api_sources
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as c:
        yield c


@pytest.fixture
def admin(client):
    """Client authenticated as the default admin."""
    token = client.post("/api/admin/login", json={"username": "admin", "password": "admin"}).json()["token"]
    client.headers["Authorization"] = "Bearer " + token
    return client


def seed_world(db, n_players=3, owned=None, status="official", detail=None, verified=True):
    """Players 1..n each own common apps 100,101 (+ player specific ones).

    Returns (players, ap_games). Archipelago games "AP 100" and "AP 101" are mapped to 100/101.
    """
    players = [
        SteamPlayer(steam_id=f"7656119000000000{i:02d}", display_name=f"P{i}", library_valid=True, last_sync_status="ok")
        for i in range(n_players)
    ]
    db.add_all(players)
    steam_games = {a: SteamGame(steam_app_id=a, name=f"Game {a}") for a in (100, 101, 102, 103)}
    db.add_all(steam_games.values())
    db.flush()
    owned = owned or {}
    for p in players:
        apps = owned.get(p.id, [100, 101, 103])
        for a in apps:
            db.add(PlayerGameOwnership(player_id=p.id, game_id=steam_games[a].id))
    ap = []
    for a in (100, 101):
        g = ArchipelagoGame(name=f"AP {a}", slug=f"ap-{a}", status=status, detail_status=detail)
        db.add(g)
        db.flush()
        db.add(GameMapping(archipelago_game_id=g.id, steam_app_id=a, mapping_type="manual", confidence=1, verified=verified))
        ap.append(g)
    db.commit()
    return players, ap
