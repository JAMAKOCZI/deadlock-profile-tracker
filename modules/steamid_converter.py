"""Conversion utilities between SteamID3 (account_id) and SteamID64."""

# SteamID64 = SteamID3 + this constant
_STEAM_ID64_OFFSET = 76561197960265728


def account_id_to_steam_id64(account_id: int) -> int:
    """Convert a SteamID3 (account_id) to a SteamID64.

    Args:
        account_id: The 32-bit Steam account ID (SteamID3).

    Returns:
        The 64-bit SteamID64.

    Raises:
        ValueError: If account_id is not a positive integer.
    """
    if account_id <= 0:
        raise ValueError(f"account_id must be positive, got {account_id}")
    return account_id + _STEAM_ID64_OFFSET


def steam_id64_to_account_id(steam_id64: int) -> int:
    """Convert a SteamID64 to a SteamID3 (account_id).

    Args:
        steam_id64: The 64-bit SteamID64.

    Returns:
        The 32-bit Steam account ID (SteamID3).

    Raises:
        ValueError: If steam_id64 is not larger than the offset constant.
    """
    if steam_id64 <= _STEAM_ID64_OFFSET:
        raise ValueError(f"steam_id64 must be > {_STEAM_ID64_OFFSET}, got {steam_id64}")
    return steam_id64 - _STEAM_ID64_OFFSET
