import json

import httpx
import pytest

from app.integrations.archipelago.base import ArchipelagoGameData, SourceFetchError
from app.integrations.archipelago.library import GamesLibrarySource, parse_library_html, parse_library_json
from app.integrations.archipelago.official import OfficialArchipelagoSource, parse_official_games
from app.integrations.archipelago.wiki import WikiArchipelagoSource, parse_category_members
from app.models import ArchipelagoGame, GameMapping, SteamGame
from app.normalize import normalize_name, slugify
from app.services.archipelago_service import ArchipelagoService, deduplicate
from app.services.mapping_service import MappingService

OFFICIAL_HTML = """
<html><body><h1>Games</h1>
<h2 id="A Link to the Past">A Link to the Past</h2><p>desc</p>
<h2 id="Hollow Knight">Hollow Knight</h2>
<h2>Games</h2></body></html>
"""


class StaticSource:
    def __init__(self, name, trust, games=None, error=None):
        self.name, self.url, self.type, self.trust_level = name, f"https://x/{name}", "test", trust
        self._games, self._error = games or [], error

    async def fetch_games(self):
        if self._error:
            raise self._error
        return list(self._games)


def test_normalize_and_slug():
    assert normalize_name("The Legend of Zelda™: A Link to the Past") == "legend of zelda a link to the past"
    assert slugify("Hollow Knight") == "hollow-knight"
    assert normalize_name("Pokémon & Friends") == "pokemon and friends"


def test_parse_official():
    games = parse_official_games(OFFICIAL_HTML)
    assert [g.name for g in games] == ["A Link to the Past", "Hollow Knight"]
    assert all(g.status == "official" for g in games)


def test_parse_wiki_and_pagination():
    payload = {"query": {"categorymembers": [{"pageid": 5, "title": "Game A"}]}, "continue": {"cmcontinue": "x"}}
    games, cont = parse_category_members(payload)
    assert games[0].external_id == "5" and games[0].status == "community" and cont == "x"


def test_parse_library_json_and_html():
    games = parse_library_json({"games": [{"name": "Foo", "status": "Stable", "steam_app_id": "12"}, {"x": 1}]})
    assert len(games) == 1 and games[0].detail_status == "stable" and games[0].steam_app_id == 12
    assert [g.name for g in parse_library_html("<h3>Bar</h3><div class='game-title'>Baz</div>")] == ["Bar", "Baz"]


def test_deduplicate_within_source():
    out = deduplicate(
        [
            ArchipelagoGameData("Hollow Knight", status="community"),
            ArchipelagoGameData("hollow  knight", status="official", description="d"),
        ]
    )
    assert len(out) == 1 and out[0].status == "official" and out[0].description == "d"


def _fetch(source, handler):
    import asyncio

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            source._client = c
            return await source.fetch_games()

    return asyncio.run(go())


def test_sources_over_mock_http():
    assert len(_fetch(OfficialArchipelagoSource(), lambda r: httpx.Response(200, text=OFFICIAL_HTML))) == 2
    wiki = {"query": {"categorymembers": [{"pageid": 1, "title": "G"}]}}
    assert len(_fetch(WikiArchipelagoSource(), lambda r: httpx.Response(200, json=wiki))) == 1
    assert len(_fetch(GamesLibrarySource(), lambda r: httpx.Response(200, text=json.dumps([{"name": "Z"}])))) == 1


def test_source_http_error_and_empty():
    with pytest.raises(SourceFetchError):
        _fetch(OfficialArchipelagoSource(), lambda r: httpx.Response(500))
    with pytest.raises(SourceFetchError):
        _fetch(OfficialArchipelagoSource(), lambda r: httpx.Response(200, text="<p>nothing</p>"))


def test_sync_dedup_across_sources_and_trust(db):
    official = StaticSource("off", "official", [ArchipelagoGameData("Hollow Knight", status="official")])
    comm = StaticSource(
        "comm",
        "community",
        [ArchipelagoGameData("hollow knight", status="community", detail_status="stable", steam_app_id=367520)],
    )
    results = ArchipelagoService(db, [comm, official]).sync()
    assert [r["status"] for r in results] == ["ok", "ok"]
    games = db.query(ArchipelagoGame).all()
    assert len(games) == 1 and games[0].status == "official"
    assert games[0].source.name == "off"
    mapping = db.query(GameMapping).one()
    assert mapping.steam_app_id == 367520 and mapping.verified and mapping.mapping_type == "imported"


def test_failing_source_keeps_old_data_and_others_work(db):
    good = StaticSource("good", "community", [ArchipelagoGameData("Game One", status="community")])
    ArchipelagoService(db, [good]).sync()
    bad = StaticSource("bad", "official", error=SourceFetchError("boom"))
    good2 = StaticSource("good", "community", [ArchipelagoGameData("Game Two", status="community")])
    results = {r["source"]: r for r in ArchipelagoService(db, [bad, good2]).sync()}
    assert results["bad"]["status"] == "error" and "boom" in results["bad"]["error"]
    assert results["good"]["status"] == "ok"
    assert {g.name for g in db.query(ArchipelagoGame)} == {"Game One", "Game Two"}


def test_sync_preserves_manual_mapping_and_disabled(db):
    src = StaticSource("s", "community", [ArchipelagoGameData("Game One", status="community")])
    ArchipelagoService(db, [src]).sync()
    game = db.query(ArchipelagoGame).one()
    MappingService(db).create(game.id, 555)
    game.enabled = False
    db.commit()
    ArchipelagoService(db, [src]).sync()
    db.refresh(game)
    assert not game.enabled
    assert [m.steam_app_id for m in db.query(GameMapping)] == [555]


def test_name_matching_is_unverified_and_ambiguity_flagged(db):
    db.add_all(
        [
            SteamGame(steam_app_id=1, name="Hollow Knight"),
            SteamGame(steam_app_id=2, name="Dupe"),
            SteamGame(steam_app_id=3, name="Dupe™"),
        ]
    )
    db.add_all([ArchipelagoGame(name="Hollow Knight", slug="hk"), ArchipelagoGame(name="Dupe", slug="dupe")])
    db.commit()
    assert MappingService(db).auto_match_by_name() == 3
    maps = db.query(GameMapping).all()
    assert all(not m.verified and m.mapping_type == "guessed" for m in maps)
    assert {m.steam_app_id: m.confidence for m in maps}[1] > {m.steam_app_id: m.confidence for m in maps}[2]
    assert MappingService(db).auto_match_by_name() == 0
