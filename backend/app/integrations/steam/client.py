from dataclasses import dataclass
from typing import Any

import httpx

from app.integrations.steam.errors import (
    SteamLibraryPrivate,
    SteamNotConfigured,
    SteamPlayerNotFound,
    SteamRateLimited,
    SteamTimeout,
    SteamUnavailable,
)

BASE_URL = "https://api.steampowered.com"
HEADER_IMAGE = "https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id}/header.jpg"


@dataclass(frozen=True)
class SteamProfile:
    steam_id: str
    display_name: str
    profile_url: str | None
    avatar_url: str | None
    is_public: bool


@dataclass(frozen=True)
class SteamOwnedGame:
    app_id: int
    name: str
    header_image_url: str


class SteamClient:
    """Thin HTTPX wrapper around the official Steam Web API (sync, used from worker threads)."""

    def __init__(self, api_key: str, timeout: float = 15.0, client: httpx.Client | None = None):
        self._api_key = api_key
        self._client = client or httpx.Client(timeout=timeout, base_url=BASE_URL)

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self._api_key:
            raise SteamNotConfigured("STEAM_API_KEY n'est pas configurée.")
        try:
            response = self._client.get(path, params={**params, "key": self._api_key})
        except httpx.TimeoutException as exc:
            raise SteamTimeout("Délai dépassé lors de l'appel à Steam.") from None
        except httpx.HTTPError:
            raise SteamUnavailable("Erreur réseau lors de l'appel à Steam.") from None
        if response.status_code == 429:
            raise SteamRateLimited("Steam limite le nombre de requêtes (rate limit).")
        if response.status_code in (401, 403):
            # Steam returns 403 for an invalid key, and sometimes for private data.
            raise SteamUnavailable("Steam a refusé la requête (clé API invalide ?).")
        if response.status_code >= 500:
            raise SteamUnavailable("Steam est indisponible.")
        if response.status_code >= 400:
            raise SteamUnavailable(f"Réponse Steam inattendue ({response.status_code}).")
        try:
            data = response.json()
        except ValueError:
            raise SteamUnavailable("Réponse Steam invalide.") from None
        if not isinstance(data, dict):
            raise SteamUnavailable("Réponse Steam invalide.")
        return data

    def resolve_vanity(self, vanity: str) -> str:
        data = self._get("/ISteamUser/ResolveVanityURL/v1/", {"vanityurl": vanity})
        resp = data.get("response") or {}
        if resp.get("success") == 1 and resp.get("steamid"):
            return str(resp["steamid"])
        raise SteamPlayerNotFound("Aucun profil Steam ne correspond à cette vanity URL.")

    def get_profile(self, steam_id: str) -> SteamProfile:
        data = self._get("/ISteamUser/GetPlayerSummaries/v2/", {"steamids": steam_id})
        players = (data.get("response") or {}).get("players") or []
        if not players:
            raise SteamPlayerNotFound("Profil Steam introuvable.")
        p = players[0]
        return SteamProfile(
            steam_id=str(p.get("steamid", steam_id)),
            display_name=p.get("personaname") or steam_id,
            profile_url=p.get("profileurl"),
            avatar_url=p.get("avatarfull") or p.get("avatar"),
            is_public=p.get("communityvisibilitystate") == 3,
        )

    def get_owned_games(self, steam_id: str) -> list[SteamOwnedGame]:
        data = self._get(
            "/IPlayerService/GetOwnedGames/v1/",
            {
                "steamid": steam_id,
                "include_appinfo": 1,
                "include_played_free_games": 1,
                "format": "json",
            },
        )
        resp = data.get("response")
        # A private profile/library yields an empty response object (no game_count key),
        # which must not be confused with an empty library (game_count == 0).
        if not isinstance(resp, dict) or "game_count" not in resp:
            raise SteamLibraryPrivate(
                "Impossible de récupérer la bibliothèque : le profil ou la bibliothèque Steam est privé."
            )
        games: list[SteamOwnedGame] = []
        for item in resp.get("games") or []:
            app_id = item.get("appid")
            if not isinstance(app_id, int):
                continue
            games.append(
                SteamOwnedGame(
                    app_id=app_id,
                    name=item.get("name") or f"App {app_id}",
                    header_image_url=HEADER_IMAGE.format(app_id=app_id),
                )
            )
        return games

    def close(self) -> None:
        self._client.close()
