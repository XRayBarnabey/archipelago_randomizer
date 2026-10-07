import pytest
from sqlalchemy import select

from app.integrations.archipelago.official import OfficialArchipelagoSource, parse_official_games
from app.integrations.archipelago.registry import default_sources
from app.models import AdminCredential, ArchipelagoSourceRecord, Draw, DrawParticipant
from app.services.archipelago_service import ArchipelagoService
from tests.conftest import seed_world

PROTECTED = [
    ("get", "/api/archipelago/games"),
    ("get", "/api/archipelago/status"),
    ("get", "/api/archipelago/sources"),
    ("post", "/api/archipelago/sync"),
    ("patch", "/api/archipelago/games/1"),
    ("get", "/api/mappings"),
    ("post", "/api/mappings"),
    ("post", "/api/mappings/auto-match"),
    ("put", "/api/mappings/1"),
    ("delete", "/api/mappings/1"),
    ("get", "/api/admin/session"),
    ("post", "/api/admin/password"),
    ("post", "/api/admin/logo"),
    ("delete", "/api/admin/logo"),
]


@pytest.mark.parametrize("method,path", PROTECTED)
def test_admin_routes_require_auth(client, method, path):
    r = getattr(client, method)(path)
    assert r.status_code == 401
    assert r.json()["error"] == "UNAUTHORIZED"


def test_invalid_token_rejected(client):
    r = client.get("/api/admin/session", headers={"Authorization": "******"})
    assert r.status_code == 401


def test_public_routes_stay_open(client, db):
    seed_world(db)
    assert client.get("/api/players").status_code == 200
    assert client.get("/api/draws").status_code == 200


def test_default_credentials_seeded_with_hash_only(client, db):
    r = client.post("/api/admin/login", json={"username": "admin", "password": "admin"})
    assert r.status_code == 200
    body = r.json()
    assert body["default_credentials"] is True and body["token"]
    cred = db.scalar(select(AdminCredential))
    assert cred.username == "admin"
    assert "admin" != cred.password_hash and cred.password_hash.startswith("scrypt$")
    assert db.query(AdminCredential).count() == 1


def test_login_failure_and_session(client):
    assert client.post("/api/admin/login", json={"username": "admin", "password": "nope"}).status_code == 401
    assert client.post("/api/admin/login", json={"username": "x", "password": "admin"}).status_code == 401
    token = client.post("/api/admin/login", json={"username": "admin", "password": "admin"}).json()["token"]
    r = client.get("/api/admin/session", headers={"Authorization": "Bearer " + token})
    assert r.status_code == 200 and r.json()["username"] == "admin" and "token" not in {k for k, v in r.json().items() if v}
    assert client.post("/api/admin/logout", headers={"Authorization": "Bearer " + token}).status_code == 204


def test_login_throttled_after_repeated_failures(client):
    for _ in range(5):
        assert client.post("/api/admin/login", json={"username": "admin", "password": "bad"}).status_code == 401
    r = client.post("/api/admin/login", json={"username": "admin", "password": "admin"})
    assert r.status_code == 429 and r.json()["error"] == "TOO_MANY_ATTEMPTS"


def test_password_change(client, admin):
    base = {"current_password": "admin", "new_password": "s3cret!", "confirm_password": "s3cret!"}
    assert client.post("/api/admin/password", json={**base, "current_password": "bad"}).status_code == 401
    assert client.post("/api/admin/password", json={**base, "confirm_password": "other"}).status_code == 422
    assert client.post("/api/admin/password", json={**base, "new_password": "a", "confirm_password": "a"}).status_code == 422
    old_headers = dict(client.headers)
    r = client.post("/api/admin/password", json={**base, "new_username": "boss"})
    assert r.status_code == 200 and r.json()["default_credentials"] is False
    # old token is invalidated, new token works
    assert client.get("/api/admin/session", headers=old_headers).status_code == 401
    assert client.get("/api/admin/session", headers={"Authorization": "Bearer " + r.json()["token"]}).status_code == 200
    assert client.post("/api/admin/login", json={"username": "admin", "password": "admin"}).status_code == 401
    ok = client.post("/api/admin/login", json={"username": "boss", "password": "s3cret!"})
    assert ok.status_code == 200 and ok.json()["default_credentials"] is False


def test_secret_key_from_settings_signs_tokens(client, settings):
    token = client.post("/api/admin/login", json={"username": "admin", "password": "admin"}).json()["token"]
    settings.admin_secret_key = "another-secret"
    assert client.get("/api/admin/session", headers={"Authorization": "Bearer " + token}).status_code == 401


def test_clear_history_resets_exclusion(client, db):
    players, _ = seed_world(db, n_players=2)
    ids = [p.id for p in players]
    filters = {"mode": "extended", "exclude_drawn": True}
    assert client.post("/api/draw", json={"player_ids": ids, "filters": filters}).status_code == 200
    assert client.post("/api/draw/per-player", json={"player_ids": ids, "filters": filters}).status_code in (200, 409)
    assert db.query(Draw).count() >= 1
    r = client.delete("/api/draws")
    assert r.status_code == 200 and r.json()["deleted"] >= 1
    db.expire_all()
    assert db.query(Draw).count() == 0 and db.query(DrawParticipant).count() == 0
    assert client.get("/api/draws").json() == []
    assert client.delete("/api/draws").json() == {"deleted": 0}
    common = client.post("/api/selection/common-games", json={"player_ids": ids, "filters": filters}).json()
    assert common["eligible_games_count"] == 2


def test_official_games_source_registered_and_idempotent(db, settings):
    sources = default_sources(settings)
    official = [s for s in sources if isinstance(s, OfficialArchipelagoSource)]
    assert len(official) == 1 and official[0].url == "https://archipelago.gg/games"
    service = ArchipelagoService(db, sources)
    service.ensure_sources()
    service.ensure_sources()
    records = list(db.scalars(select(ArchipelagoSourceRecord).where(ArchipelagoSourceRecord.url == "https://archipelago.gg/games")))
    assert len(records) == 1 and records[0].enabled is True


def test_official_parser_falls_back_to_list_items_and_links():
    assert [g.name for g in parse_official_games("<ul><li>Hollow Knight</li><li>Zillion</li></ul>")] == ["Hollow Knight", "Zillion"]
    assert [g.name for g in parse_official_games('<a href="/g/1">Timespinner</a>')] == ["Timespinner"]


PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def test_logo_lifecycle(client, admin):
    assert client.get("/api/logo").status_code == 404
    r = client.post("/api/admin/logo", files={"file": ("logo.png", PNG, "image/png")})
    assert r.status_code == 204
    r = client.get("/api/logo", headers={"Authorization": ""})
    assert r.status_code == 200 and r.content == PNG and r.headers["content-type"] == "image/png"
    new = PNG + b"x"
    assert client.post("/api/admin/logo", files={"file": ("l.png", new, "image/png")}).status_code == 204
    assert client.get("/api/logo").content == new
    assert client.delete("/api/admin/logo").status_code == 204
    assert client.get("/api/logo").status_code == 404


def test_logo_rejects_invalid(client, admin):
    r = client.post("/api/admin/logo", files={"file": ("a.txt", b"hello", "text/plain")})
    assert r.status_code == 422
    r = client.post("/api/admin/logo", files={"file": ("a.png", b"not a png", "image/png")})
    assert r.status_code == 422
    big = PNG + b"\x00" * (2 * 1024 * 1024)
    r = client.post("/api/admin/logo", files={"file": ("a.png", big, "image/png")})
    assert r.status_code == 422
    assert client.get("/api/logo").status_code == 404
