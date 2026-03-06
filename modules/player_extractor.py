"""Extract players from raw match data returned by the Deadlock API."""

from __future__ import annotations

from typing import Any, Dict, List

from models.player import Player


def extract_players(match_data: Dict[str, Any]) -> List[Player]:
    """Parse the ``players`` array from a match payload and return
    a list of :class:`Player` instances.

    Works with both active-match and match-history payloads.

    Args:
        match_data: A dict representing an active match or a match
            history entry as returned by the Deadlock API.

    Returns:
        A list of :class:`Player` objects (up to 12 for a standard
        6 v 6 match).
    """
    raw_players: List[Dict[str, Any]] = match_data.get("players", [])
    players: List[Player] = []

    for rp in raw_players:
        account_id = rp.get("account_id")
        if account_id is None:
            continue

        player = Player(
            account_id=int(account_id),
            team=int(rp.get("team", 0)),
            hero_id=int(rp.get("hero_id", 0)),
            abandoned=bool(rp.get("abandoned", False)),
        )
        # If the payload already contains per-player combat stats
        # (match-history entries), populate them.
        player.kills = int(rp.get("player_kills", 0))
        player.deaths = int(rp.get("player_deaths", 0))
        player.assists = int(rp.get("player_assists", 0))

        players.append(player)

    return players
