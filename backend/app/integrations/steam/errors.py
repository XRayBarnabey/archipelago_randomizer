class SteamError(Exception):
    """Base error for Steam integration problems. Messages never contain secrets."""

    code = "STEAM_ERROR"


class SteamNotConfigured(SteamError):
    code = "STEAM_API_KEY_MISSING"


class InvalidSteamInput(SteamError):
    code = "INVALID_STEAM_INPUT"


class SteamPlayerNotFound(SteamError):
    code = "STEAM_PROFILE_NOT_FOUND"


class SteamLibraryPrivate(SteamError):
    code = "STEAM_LIBRARY_PRIVATE"


class SteamUnavailable(SteamError):
    code = "STEAM_UNAVAILABLE"


class SteamTimeout(SteamUnavailable):
    code = "STEAM_TIMEOUT"


class SteamRateLimited(SteamUnavailable):
    code = "STEAM_RATE_LIMITED"
