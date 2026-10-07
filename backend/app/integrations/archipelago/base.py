from dataclasses import dataclass
from typing import Protocol

OFFICIAL = "official"
COMMUNITY = "community"
UNKNOWN = "unknown"
STATUS_RANK = {UNKNOWN: 0, COMMUNITY: 1, OFFICIAL: 2}
DETAIL_STATUSES = {"stable", "unstable", "untested", "deprecated"}


@dataclass
class ArchipelagoGameData:
    name: str
    external_id: str | None = None
    description: str | None = None
    status: str = UNKNOWN
    detail_status: str | None = None
    version: str | None = None
    steam_app_id: int | None = None
    url: str | None = None


class SourceFetchError(Exception):
    pass


class ArchipelagoSource(Protocol):
    """A provider of Archipelago game data. Implement and register to add a source."""

    name: str
    url: str
    type: str
    trust_level: str

    async def fetch_games(self) -> list[ArchipelagoGameData]: ...


def clean_detail_status(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip().lower()
    return value if value in DETAIL_STATUSES else None
