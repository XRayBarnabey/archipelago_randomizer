import httpx
import pytest

from app.integrations.steam.client import SteamClient
from app.integrations.steam.errors import (
    InvalidSteamInput,
    SteamLibraryPrivate,
    SteamNotConfigured,
    SteamPlayerNotFound,
    SteamRateLimited,
    SteamTimeout,
    SteamUnavailable,
)
from app.integrations.steam.ids import parse_steam_input
from app.services.steam_service import SteamService
from tests.conftest import game

SID = "76561198000000001"


def test_parse_steamid64():
    assert parse_steam_input(SID).steam_id == SID


@pytest.mark.parametrize(
    "raw,expected",
    [
        (f"https://steamcommunity.com/profiles/{SID}/", ("steam_id", SID)),
        (f"steamcommunity.com/profiles/{SID}", ("steam_id", SID)),
        ("https://steamcommunity.com/id/some_name/", ("vanity", "some_name")),
        ("some_name", ("vanity", "some_name")),
    ],
)
def test_parse_inputs(raw, expected):
    parsed = parse_steam_input(raw)
    assert getattr(parsed, expected[0]) == expected[1]


@pytest.mark.parametrize("raw", ["", "  ", "https://evil.example/id/foo", "a", "https://steamcommunity.com/groups/x", "bad name!"])
def test_parse_invalid(raw):
    with pytest.raises(InvalidSteamInput):
        parse_steam_input(raw)


def make_client(handler, key="k"):
    return SteamClient(key, client=httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.steampowered.com"))


def test_missing_key():
    with pytest.raises(SteamNotConfigured):
        make_client(lambda r: httpx.Response(200, json={}), key="").get_profile(SID)


def test_resolve_vanity():
    c = make_client(lambda r: httpx.Response(200, json={"response": {"success": 1, "steamid": SID}}))
    assert c.resolve_vanity("x") == SID
    c = make_client(lambda r: httpx.Response(200, json={"response": {"success": 42}}))
    with pytest.raises(SteamPlayerNotFound):
        c.resolve_vanity("x")


def test_profile_not_found():
    c = make_client(lambda r: httpx.Response(200, json={"response": {"players": []}}))
    with pytest.raises(SteamPlayerNotFound):
        c.get_profile(SID)


def test_owned_games_private_vs_empty():
    private = make_client(lambda r: httpx.Response(200, json={"response": {}}))
    with pytest.raises(SteamLibraryPrivate):
        private.get_owned_games(SID)
    empty = make_client(lambda r: httpx.Response(200, json={"response": {"game_count": 0}}))
    assert empty.get_owned_games(SID) == []


def test_owned_games_parsing():
    payload = {"response": {"game_count": 1, "games": [{"appid": 10, "name": "Counter-Strike"}]}}
    games = make_client(lambda r: httpx.Response(200, json=payload)).get_owned_games(SID)
    assert games[0].app_id == 10 and games[0].name == "Counter-Strike"


@pytest.mark.parametrize(
    "status,exc", [(429, SteamRateLimited), (500, SteamUnavailable), (503, SteamUnavailable), (403, SteamUnavailable)]
)
def test_http_errors(status, exc):
    with pytest.raises(exc):
        make_client(lambda r: httpx.Response(status)).get_owned_games(SID)


def test_timeout_and_network_errors_do_not_leak_key():
    def timeout(request):
        raise httpx.ReadTimeout("boom", request=request)

    def network(request):
        raise httpx.ConnectError("boom", request=request)

    with pytest.raises(SteamTimeout) as e1:
        make_client(timeout, key="SECRETKEY").get_owned_games(SID)
    with pytest.raises(SteamUnavailable) as e2:
        make_client(network, key="SECRETKEY").get_owned_games(SID)
    assert "SECRETKEY" not in str(e1.value) + str(e2.value)


def test_service_sync_and_keep_data_on_error(db, steam, settings):
    steam.profiles[SID] = "Alice"
    steam.libraries[SID] = [game(1), game(2)]
    service = SteamService(db, steam, settings)
    player = service.add_player(SID)
    assert not player.library_valid

    res = service.sync_player(player.id, force=True)
    assert res.status == "ok" and res.games_count == 2
    assert player.library_valid and player.last_synced_at

    steam.libraries[SID] = SteamUnavailable("down")
    res = service.sync_player(player.id, force=True)
    assert res.status == "error" and res.games_count == 2
    db.refresh(player)
    assert player.library_valid and player.last_sync_status == "error"

    steam.libraries[SID] = SteamLibraryPrivate("Impossible de récupérer la bibliothèque : privé")
    assert service.sync_player(player.id, force=True).status == "private"

    steam.libraries[SID] = [game(2), game(3)]
    assert service.sync_player(player.id, force=True).games_count == 2


def test_private_first_sync_is_not_a_valid_empty_library(db, steam, settings):
    steam.profiles[SID] = "Bob"
    steam.libraries[SID] = SteamLibraryPrivate("private")
    service = SteamService(db, steam, settings)
    player = service.add_player(SID)
    res = service.sync_player(player.id)
    assert res.status == "private"
    db.refresh(player)
    assert not player.library_valid and player.last_synced_at is None


def test_empty_library_is_valid(db, steam, settings):
    steam.profiles[SID] = "Bob"
    service = SteamService(db, steam, settings)
    player = service.add_player(SID)
    assert service.sync_player(player.id).status == "ok"
    assert player.library_valid


def test_cache_prevents_steam_calls(db, steam, settings):
    steam.profiles[SID] = "Bob"
    steam.libraries[SID] = [game(1)]
    service = SteamService(db, steam, settings)
    player = service.add_player(SID)
    service.sync_player(player.id)
    calls = steam.calls
    assert service.sync_player(player.id).status == "cached"
    assert steam.calls == calls
    service.sync_player(player.id, force=True)
    assert steam.calls == calls + 1
