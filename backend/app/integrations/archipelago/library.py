import json

import httpx

from app.integrations.archipelago.base import (
    COMMUNITY,
    ArchipelagoGameData,
    SourceFetchError,
    clean_detail_status,
)
from app.integrations.archipelago.html import collect
from app.integrations.archipelago.official import _ClientCtx
from app.normalize import slugify

TITLE_CLASSES = {"game-title", "game-name", "card-title"}


def _int_or_none(value) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def parse_library_json(payload) -> list[ArchipelagoGameData]:
    items = payload.get("games") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        return []
    games = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or item.get("title") or item.get("game")
        if not name:
            continue
        games.append(
            ArchipelagoGameData(
                name=str(name),
                external_id=str(item.get("id") or item.get("slug") or slugify(str(name))),
                description=item.get("description"),
                status=COMMUNITY,
                detail_status=clean_detail_status(item.get("status")),
                version=item.get("version"),
                steam_app_id=_int_or_none(item.get("steam_app_id") or item.get("steamAppId") or item.get("steam_id")),
                url=item.get("url"),
            )
        )
    return games


def parse_library_html(html: str) -> list[ArchipelagoGameData]:
    def is_title(tag, attrs):
        classes = set(attrs.get("class", "").split())
        return bool(classes & TITLE_CLASSES) or tag == "h3"

    games: dict[str, ArchipelagoGameData] = {}
    for _t, attrs, text in collect(html, is_title):
        slug = slugify(text)
        if slug and slug not in games:
            games[slug] = ArchipelagoGameData(name=text, external_id=slug, status=COMMUNITY)
    return list(games.values())


class GamesLibrarySource:
    """Archipelago Games Library: JSON when available, best-effort HTML otherwise."""

    name = "Archipelago Games Library"
    url = "https://mk-404.github.io/Archipelago-Games-Library/"
    type = "html"
    trust_level = COMMUNITY

    def __init__(self, client: httpx.AsyncClient | None = None, timeout: float = 15.0):
        self._client = client
        self._timeout = timeout

    async def fetch_games(self) -> list[ArchipelagoGameData]:
        try:
            async with _ClientCtx(self._client, self._timeout) as client:
                response = await client.get(self.url)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise SourceFetchError(f"{type(exc).__name__} lors de la récupération de {self.url}") from None
        text = response.text
        games: list[ArchipelagoGameData] = []
        if text.lstrip().startswith(("[", "{")):
            try:
                games = parse_library_json(json.loads(text))
            except ValueError:
                games = []
        else:
            games = parse_library_html(text)
        if not games:
            raise SourceFetchError("Aucun jeu trouvé : le format de la source a peut-être changé.")
        return games
