import httpx

from app.integrations.archipelago.base import COMMUNITY, ArchipelagoGameData, SourceFetchError
from app.integrations.archipelago.official import _ClientCtx

API_URL = "https://archipelago.miraheze.org/w/api.php"


def parse_category_members(payload: dict) -> tuple[list[ArchipelagoGameData], str | None]:
    members = (payload.get("query") or {}).get("categorymembers") or []
    games = [
        ArchipelagoGameData(
            name=m["title"],
            external_id=str(m.get("pageid") or m["title"]),
            status=COMMUNITY,
            url=f"https://archipelago.miraheze.org/wiki/{m['title'].replace(' ', '_')}",
        )
        for m in members
        if m.get("title")
    ]
    cont = (payload.get("continue") or {}).get("cmcontinue")
    return games, cont


class WikiArchipelagoSource:
    """Uses the structured MediaWiki API rather than scraping the category HTML page."""

    name = "Archipelago Wiki"
    url = "https://archipelago.miraheze.org/wiki/Category:Implementations"
    type = "mediawiki"
    trust_level = COMMUNITY

    def __init__(self, client: httpx.AsyncClient | None = None, timeout: float = 15.0, api_url: str = API_URL):
        self._client = client
        self._timeout = timeout
        self._api_url = api_url

    async def fetch_games(self) -> list[ArchipelagoGameData]:
        games: list[ArchipelagoGameData] = []
        cont: str | None = None
        try:
            async with _ClientCtx(self._client, self._timeout) as client:
                for _ in range(20):
                    params = {
                        "action": "query",
                        "list": "categorymembers",
                        "cmtitle": "Category:Implementations",
                        "cmlimit": "500",
                        "cmnamespace": "0",
                        "cmtype": "page",
                        "format": "json",
                    }
                    if cont:
                        params["cmcontinue"] = cont
                    response = await client.get(self._api_url, params=params)
                    response.raise_for_status()
                    page, cont = parse_category_members(response.json())
                    games.extend(page)
                    if not cont:
                        break
        except (httpx.HTTPError, ValueError) as exc:
            raise SourceFetchError(f"{type(exc).__name__} lors de la récupération du wiki") from None
        if not games:
            raise SourceFetchError("Aucune implémentation trouvée dans la catégorie du wiki.")
        return games
