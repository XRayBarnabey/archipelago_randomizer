from app.config import Settings
from app.integrations.archipelago.base import ArchipelagoSource
from app.integrations.archipelago.library import GamesLibrarySource
from app.integrations.archipelago.official import OfficialArchipelagoSource
from app.integrations.archipelago.wiki import WikiArchipelagoSource


def default_sources(settings: Settings) -> list[ArchipelagoSource]:
    t = settings.http_timeout
    return [
        OfficialArchipelagoSource(timeout=t),
        WikiArchipelagoSource(timeout=t),
        GamesLibrarySource(timeout=t),
    ]
