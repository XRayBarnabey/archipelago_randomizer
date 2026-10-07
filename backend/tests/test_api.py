from app.integrations.archipelago.base import ArchipelagoGameData
from app.integrations.steam.errors import SteamLibraryPrivate
from tests.conftest import game, seed_world
from tests.test_archipelago import StaticSource

SID = "76561198000000001"


def add_player(client, steam, sid=SID, name="Alice", vanity=None):
    steam.profiles[sid] = name
    if vanity:
        steam.vanities[vanity] = sid
    return client.post("/api/players", json={"input": vanity or sid})


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/openapi.json").status_code == 200


def test_player_lifecycle(client, steam):
    r = add_player(client, steam)
    assert r.status_code == 201 and r.json()["display_name"] == "Alice" and r.json()["game_count"] == 0
    pid = r.json()["id"]
    assert add_player(client, steam).status_code == 409
    steam.libraries[SID] = [game(1), game(2), game(3)]
    s = client.post(f"/api/players/{pid}/sync", params={"force": True}).json()
    assert s["status"] == "ok" and s["games_count"] == 3
    assert client.get(f"/api/players/{pid}").json()["game_count"] == 3
    assert len(client.get("/api/players").json()) == 1
    assert client.post("/api/players/sync", params={"force": True}).json()[0]["status"] == "ok"
    assert client.delete(f"/api/players/{pid}").status_code == 204
    assert client.get(f"/api/players/{pid}").status_code == 404


def test_add_player_by_vanity_url_and_errors(client, steam):
    steam.profiles[SID] = "Alice"
    steam.vanities["alice"] = SID
    assert client.post("/api/players", json={"input": "https://steamcommunity.com/id/alice"}).status_code == 201
    assert client.post("/api/players", json={"input": "https://steamcommunity.com/id/unknown"}).status_code == 404
    assert client.post("/api/players", json={"input": "!!"}).status_code == 422
    assert client.post("/api/players", json={}).status_code == 422


def test_private_library_reported(client, steam):
    pid = add_player(client, steam).json()["id"]
    steam.libraries[SID] = SteamLibraryPrivate("privé")
    body = client.post(f"/api/players/{pid}/sync").json()
    assert body["status"] == "private" and body["error_code"] == "STEAM_LIBRARY_PRIVATE"
    r = client.post("/api/selection/common-games", json={"player_ids": [pid]})
    assert r.status_code == 409 and r.json()["error"] == "LIBRARY_UNAVAILABLE"


def test_common_games_and_draw(client, db):
    players, _ = seed_world(db, 3)
    ids = [p.id for p in players]
    r = client.post("/api/selection/common-games", json={"player_ids": ids})
    body = r.json()
    assert r.status_code == 200 and body["eligible_games_count"] == 2 and body["players_count"] == 3
    assert body["games"][0]["steam_url"].startswith("https://store.steampowered.com/app/")
    assert body["games"][0]["owned_by_count"] == 3

    d = client.post("/api/draw", json={"player_ids": ids, "filters": {"mode": "recommended"}}).json()
    assert d["selected_game"]["steam_app_id"] in (100, 101)
    assert d["eligible_games_count"] == 2 and d["players_count"] == 3 and len(d["owners"]) == 3
    assert d["selected_game"]["mapping_verified"] is True

    hist = client.get("/api/draws").json()
    assert len(hist) == 1 and len(hist[0]["players"]) == 3 and hist[0]["filters"]["mode"] == "recommended"


def test_draw_exclude_drawn_then_409(client, db):
    players, _ = seed_world(db, 2)
    body = {"player_ids": [p.id for p in players], "filters": {"exclude_drawn": True}}
    assert client.post("/api/draw", json=body).status_code == 200
    assert client.post("/api/draw", json=body).status_code == 200
    r = client.post("/api/draw", json=body)
    assert r.status_code == 409
    assert r.json() == {
        "error": "NO_COMMON_GAMES",
        "message": "Aucun jeu compatible Archipelago n'est possédé par tous les joueurs sélectionnés.",
    }


def test_nine_players_rejected(client, db):
    players, _ = seed_world(db, 9)
    r = client.post("/api/draw", json={"player_ids": [p.id for p in players]})
    assert r.status_code == 422 and r.json()["error"] == "INVALID_PLAYER_COUNT"
    assert client.post("/api/selection/common-games", json={"player_ids": []}).status_code == 422
    assert client.post("/api/draw", json={"player_ids": [999]}).status_code == 404
    assert client.post("/api/draw", json={"player_ids": [1], "filters": {"mode": "bogus"}}).status_code == 422


def test_mappings_crud(client, db):
    _, ap = seed_world(db, 1)
    assert len(client.get("/api/mappings").json()) == 2
    r = client.post("/api/mappings", json={"archipelago_game_id": ap[0].id, "steam_app_id": 999, "verified": False})
    assert r.status_code == 201
    mid = r.json()["id"]
    assert client.post("/api/mappings", json={"archipelago_game_id": ap[0].id, "steam_app_id": 999}).status_code == 409
    assert [m["id"] for m in client.get("/api/mappings", params={"verified": False}).json()] == [mid]
    r = client.put(f"/api/mappings/{mid}", json={"verified": True})
    assert r.json()["verified"] is True
    assert client.post("/api/mappings", json={"archipelago_game_id": 9999, "steam_app_id": 1}).status_code == 404
    assert client.delete(f"/api/mappings/{mid}").status_code == 204
    assert client.delete(f"/api/mappings/{mid}").status_code == 404


def test_archipelago_sync_and_games_api(client, api_sources):
    api_sources.extend(
        [
            StaticSource("ok", "official", [ArchipelagoGameData("Game A", status="official")]),
            StaticSource("down", "community", error=__import__("app.integrations.archipelago.base", fromlist=["x"]).SourceFetchError("unavailable")),
        ]
    )
    results = {r["source"]: r["status"] for r in client.post("/api/archipelago/sync").json()}
    assert results == {"ok": "ok", "down": "error"}
    sources = {s["name"]: s for s in client.get("/api/archipelago/sources").json()}
    assert sources["down"]["last_sync_status"] == "error"
    games = client.get("/api/archipelago/games").json()
    assert games[0]["name"] == "Game A" and games[0]["source_name"] == "ok" and games[0]["steam_app_ids"] == []
    assert client.get("/api/archipelago/games", params={"unmapped": True}).json()
    gid = games[0]["id"]
    assert client.patch(f"/api/archipelago/games/{gid}", json={"enabled": False}).json()["enabled"] is False


def test_player_search_and_per_player_endpoints(client, steam):
    add_player(client, steam, name="Alice")
    add_player(client, steam, sid="76561198000000002", name="Bob")
    r = client.get("/api/players/search", params={"query": "ALI"})
    assert [p["display_name"] for p in r.json()] == ["Alice"]
    assert [p["display_name"] for p in client.get("/api/players/search", params={"query": "Bobb"}).json()] == ["Bob"]
    assert client.get("/api/players/search").status_code == 422
    assert client.post("/api/selection/player-games", json={"player_ids": [1]}).status_code == 409
    assert client.get("/api/archipelago/status").json()["verified_mappings_count"] == 0
