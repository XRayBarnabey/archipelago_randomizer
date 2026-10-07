import pytest

from app.errors import AppError, ValidationFailed
from app.models import ArchipelagoGame, Draw
from app.services.draw_service import DrawService, NoCommonGames
from app.services.eligibility_service import EligibilityService, Filters
from tests.conftest import seed_world


@pytest.mark.parametrize("n", range(1, 9))
def test_intersection_one_to_eight(db, n):
    players, _ = seed_world(db, n)
    games = EligibilityService(db).get_eligible_games([p.id for p in players])
    assert [g.steam_app_id for g in games] == [100, 101]


def test_nine_players_refused(db):
    players, _ = seed_world(db, 9)
    with pytest.raises(ValidationFailed):
        EligibilityService(db).get_eligible_games([p.id for p in players])


def test_zero_players_refused(db):
    with pytest.raises(ValidationFailed):
        EligibilityService(db).get_eligible_games([])


def test_intersection_excludes_game_missing_for_one_player(db):
    players, _ = seed_world(db, 3)
    seed_ids = [p.id for p in players]
    # remove 101 for player 2 by rebuilding ownership
    from app.models import PlayerGameOwnership, SteamGame
    gid = db.query(SteamGame).filter_by(steam_app_id=101).one().id
    db.query(PlayerGameOwnership).filter_by(player_id=seed_ids[2], game_id=gid).delete()
    db.commit()
    games = EligibilityService(db).get_eligible_games(seed_ids)
    assert [g.steam_app_id for g in games] == [100]


def test_no_common_games(db):
    players, _ = seed_world(db, 2, owned={})
    from app.models import PlayerGameOwnership
    db.query(PlayerGameOwnership).filter_by(player_id=players[1].id).delete()
    db.add(PlayerGameOwnership(player_id=players[1].id, game_id=4))  # steam game 102
    db.commit()
    assert EligibilityService(db).get_eligible_games([p.id for p in players]) == []


def test_invalid_library_blocks_computation(db):
    players, _ = seed_world(db, 3)
    players[1].library_valid = False
    db.commit()
    with pytest.raises(AppError) as exc:
        EligibilityService(db).get_eligible_games([p.id for p in players])
    assert exc.value.code == "LIBRARY_UNAVAILABLE"


def test_unverified_mapping_ignored(db):
    players, _ = seed_world(db, 2, verified=False)
    assert EligibilityService(db).get_eligible_games([p.id for p in players]) == []


def test_disabled_game_ignored(db):
    players, ap = seed_world(db, 2)
    ap[0].enabled = False
    db.commit()
    assert [g.steam_app_id for g in EligibilityService(db).get_eligible_games([p.id for p in players])] == [101]


@pytest.mark.parametrize(
    "status,detail,official,recommended,extended",
    [
        ("official", None, 2, 2, 2),
        ("community", "stable", 0, 2, 2),
        ("community", None, 0, 0, 2),
        ("community", "unstable", 0, 0, 2),
        ("unknown", None, 0, 0, 2),
    ],
)
def test_status_modes(db, status, detail, official, recommended, extended):
    players, _ = seed_world(db, 2, status=status, detail=detail)
    ids = [p.id for p in players]
    svc = EligibilityService(db)
    for mode, expected in (("official", official), ("recommended", recommended), ("extended", extended)):
        assert len(svc.get_eligible_games(ids, Filters(mode=mode))) == expected


def test_explicit_exclusion_and_already_drawn(db):
    players, ap = seed_world(db, 2)
    ids = [p.id for p in players]
    svc = EligibilityService(db)
    assert len(svc.get_eligible_games(ids, Filters(excluded_game_ids=[ap[0].id]))) == 1
    draws = DrawService(db, svc)
    first, chosen, count, _ = draws.draw(ids, Filters(exclude_drawn=True))
    assert count == 2
    _, second, count2, _ = draws.draw(ids, Filters(exclude_drawn=True))
    assert count2 == 1 and second.archipelago_game.id != chosen.archipelago_game.id
    with pytest.raises(NoCommonGames):
        draws.draw(ids, Filters(exclude_drawn=True))
    assert db.query(Draw).count() == 2


def test_exclude_last_n(db):
    players, _ = seed_world(db, 2)
    ids = [p.id for p in players]
    draws = DrawService(db, EligibilityService(db))
    _, first, _, _ = draws.draw(ids, Filters())
    left = EligibilityService(db).get_eligible_games(ids, Filters(exclude_last_n=1))
    assert first.archipelago_game.id not in [g.archipelago_game.id for g in left]


def test_draw_is_uniform_enough(db):
    players, _ = seed_world(db, 2)
    ids = [p.id for p in players]
    draws = DrawService(db, EligibilityService(db))
    seen = {draws.draw(ids, Filters())[1].steam_app_id for _ in range(40)}
    assert seen == {100, 101}


def test_game_without_steam_mapping_never_eligible(db):
    players, _ = seed_world(db, 2)
    db.add(ArchipelagoGame(name="No Steam", slug="no-steam", status="official"))
    db.commit()
    names = [g.archipelago_game.name for g in EligibilityService(db).get_eligible_games([p.id for p in players])]
    assert "No Steam" not in names


def test_games_per_player_and_draw(db):
    from app.models import PlayerGameOwnership, SteamGame
    players, _ = seed_world(db, 2)
    db.query(PlayerGameOwnership).filter_by(player_id=players[1].id).delete()
    g100 = db.query(SteamGame).filter_by(steam_app_id=100).one().id
    db.add(PlayerGameOwnership(player_id=players[1].id, game_id=g100))
    db.commit()
    ids = [p.id for p in players]
    _, per = EligibilityService(db).get_games_per_player(ids)
    assert [g.steam_app_id for g in per[players[0].id]] == [100, 101]
    assert [g.steam_app_id for g in per[players[1].id]] == [100]

    svc = DrawService(db, EligibilityService(db))
    _, _, chosen = svc.draw_per_player(ids, Filters(allow_duplicates=False))
    assert chosen[players[1].id].steam_app_id == 100
    assert chosen[players[0].id].steam_app_id == 101
    _, _, chosen = svc.draw_per_player(ids, Filters())
    assert chosen[players[1].id].steam_app_id == 100
    with pytest.raises(AppError) as exc:
        svc.draw_per_player(ids, Filters(allow_duplicates=False, excluded_game_ids=[per[players[0].id][1].archipelago_game.id]))
    assert exc.value.code == "DUPLICATES_UNAVOIDABLE"
    with pytest.raises(AppError) as exc:
        svc.draw_per_player(ids, Filters(excluded_game_ids=[per[players[1].id][0].archipelago_game.id]))
    assert exc.value.code == "NO_COMPATIBLE_GAMES"
