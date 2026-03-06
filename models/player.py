"""Player data model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Player:
    """Represents a player in a Deadlock match."""

    account_id: int
    team: int  # 0 or 1

    # From Deadlock API active match
    hero_id: int = 0
    abandoned: bool = False

    # From Deadlock API player profile / Steam
    persona_name: str = ""
    avatar_url: str = ""
    profile_url: str = ""
    country_code: str = ""

    # From Deadlock API match history (aggregated)
    kills: int = 0
    deaths: int = 0
    assists: int = 0
    wins: int = 0
    losses: int = 0

    # Derived helpers
    @property
    def steam_id64(self) -> int:
        """Return the SteamID64 for this player."""
        from modules.steamid_converter import account_id_to_steam_id64

        return account_id_to_steam_id64(self.account_id)

    @property
    def kda_str(self) -> str:
        """Human-readable KDA string."""
        return f"{self.kills}/{self.deaths}/{self.assists}"

    @property
    def win_rate(self) -> float:
        """Win rate as a percentage (0-100)."""
        total = self.wins + self.losses
        if total == 0:
            return 0.0
        return round(self.wins / total * 100, 1)

    @property
    def display_name(self) -> str:
        """Best available display name."""
        return self.persona_name or f"Player_{self.account_id}"
