"""Match data model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from models.player import Player


@dataclass
class Match:
    """Represents a Deadlock match with two teams of players."""

    match_id: int
    lobby_id: int = 0
    start_time: int = 0
    duration_s: int = 0
    game_mode: str = ""
    region: str = ""
    spectators: int = 0
    net_worth_team_0: int = 0
    net_worth_team_1: int = 0
    winning_team: Optional[int] = None
    players: List[Player] = field(default_factory=list)
    # True when only a single-player history row was available
    is_partial: bool = False
    # True when data came from finished-match metadata
    from_metadata: bool = False

    @property
    def team_0(self) -> List[Player]:
        """Return players on team 0."""
        return [p for p in self.players if p.team == 0]

    @property
    def team_1(self) -> List[Player]:
        """Return players on team 1."""
        return [p for p in self.players if p.team == 1]

    @property
    def is_active(self) -> bool:
        """Whether the match appears still in progress."""
        if self.is_partial:
            return False
        if self.from_metadata and self.winning_team is not None:
            return False
        if self.from_metadata and self.duration_s > 0 and self.winning_team is None:
            # Finished metadata without winner field — not "live"
            return False
        return self.winning_team is None
