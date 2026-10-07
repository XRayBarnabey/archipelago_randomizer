import httpx

from app.integrations.archipelago.base import OFFICIAL, ArchipelagoGameData, SourceFetchError
from app.integrations.archipelago.html import collect
from app.normalize import slugify

GENERIC_HEADINGS = {"games", "supported games", "archipelago", "archipelago multiworld randomizer"}


def parse_official_games(html: str) -> list[ArchipelagoGameData]:
    """archipelago.gg/games is HTML only: each game is a heading (h2/h3, id attribute preferred)."""
    items = collect(html, lambda tag, attrs: tag in ("h2", "h3"))
    if not any(text.lower() not in GENERIC_HEADINGS for _t, _a, text in items):
        # fallback when headings are absent: list items, then links
        items = collect(html, lambda tag, attrs: tag == "li") or collect(html, lambda tag, attrs: tag == "a")
        items = [(t, a, x) for t, a, x in items if len(x) <= 100]
    games: dict[str, ArchipelagoGameData] = {}
    for _tag, attrs, text in items:
        if text.lower() in GENERIC_HEADINGS:
            continue
        slug = slugify(text)
        if slug and slug not in games:
            games[slug] = ArchipelagoGameData(
                name=text, external_id=attrs.get("id") or slug, status=OFFICIAL
            )
    return list(games.values())


class OfficialArchipelagoSource:
    name = "Archipelago officiel"
    url = "https://archipelago.gg/games"
    type = "html"
    trust_level = OFFICIAL

    def __init__(self, client: httpx.AsyncClient | None = None, timeout: float = 15.0):
        self._client = client
        self._timeout = timeout

    async def fetch_games(self) -> list[ArchipelagoGameData]:
        try:
            async with self._client_ctx() as client:
                response = await client.get(self.url)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise SourceFetchError(f"{type(exc).__name__} lors de la récupération de {self.url}") from None
        games = parse_official_games(response.text)
        if not games:
            raise SourceFetchError("Aucun jeu trouvé : le format de la page a peut-être changé.")
        return games

    def _client_ctx(self):
        return _ClientCtx(self._client, self._timeout)


class _ClientCtx:
    def __init__(self, client, timeout):
        self._client, self._timeout, self._owned = client, timeout, None

    async def __aenter__(self):
        if self._client:
            return self._client
        self._owned = httpx.AsyncClient(timeout=self._timeout, follow_redirects=True)
        return self._owned

    async def __aexit__(self, *exc):
        if self._owned:
            await self._owned.aclose()
