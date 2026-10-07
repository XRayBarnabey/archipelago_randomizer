import re
from dataclasses import dataclass
from urllib.parse import urlparse

from app.integrations.steam.errors import InvalidSteamInput

STEAM_ID64_RE = re.compile(r"^7656119\d{10}$")
VANITY_RE = re.compile(r"^[A-Za-z0-9_-]{2,32}$")


@dataclass(frozen=True)
class ParsedSteamInput:
    steam_id: str | None = None
    vanity: str | None = None


def parse_steam_input(raw: str) -> ParsedSteamInput:
    """Parse a SteamID64, profile URL or vanity name. Vanity names still need resolving."""
    value = (raw or "").strip()
    if not value:
        raise InvalidSteamInput("Entrée Steam vide.")
    if STEAM_ID64_RE.match(value):
        return ParsedSteamInput(steam_id=value)

    if "/" in value or "." in value:
        candidate = value if "://" in value else f"https://{value}"
        parsed = urlparse(candidate)
        host = (parsed.hostname or "").lower()
        if host not in ("steamcommunity.com", "www.steamcommunity.com"):
            raise InvalidSteamInput("L'URL doit être une URL de profil steamcommunity.com.")
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) >= 2 and parts[0] == "profiles" and STEAM_ID64_RE.match(parts[1]):
            return ParsedSteamInput(steam_id=parts[1])
        if len(parts) >= 2 and parts[0] == "id" and VANITY_RE.match(parts[1]):
            return ParsedSteamInput(vanity=parts[1])
        raise InvalidSteamInput("URL de profil Steam non reconnue.")

    if VANITY_RE.match(value):
        return ParsedSteamInput(vanity=value)
    raise InvalidSteamInput("SteamID64, URL de profil ou vanity URL invalide.")
