"""Extract players from raw match data returned by the Deadlock API."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from models.player import Player


def extract_players(match_data: Dict[str, Any]) -> List[Player]:
    """Parse the ``players`` array from a match payload.

    Works with:

    * active-match payloads (``players`` at top level)
    * metadata payloads (``match_info.players`` or hoisted top-level)
    * both ``player_kills`` (history) and ``kills`` (metadata) field names
    * both ``team`` and ``player_team`` for side assignment
    """
    if "players" in match_data:
        raw_players: List[Any] = match_data.get("players") or []
    else:
        match_info = match_data.get("match_info")
        if isinstance(match_info, dict):
            raw_players = match_info.get("players") or []
        else:
            raw_players = []

    players: List[Player] = []

    for rp in raw_players:
        if not isinstance(rp, dict):
            continue
        account_id = rp.get("account_id")
        if account_id is None:
            continue

        team = _int_field(rp, "team", "player_team", default=0)
        hero_id = _int_field(rp, "hero_id", default=0)
        abandoned = bool(
            rp.get("abandoned")
            if rp.get("abandoned") is not None
            else rp.get("team_abandoned", False)
        )

        player = Player(
            account_id=int(account_id),
            team=team,
            hero_id=hero_id,
            abandoned=abandoned,
        )
        player.kills = _int_field(rp, "player_kills", "kills", default=0)
        player.deaths = _int_field(rp, "player_deaths", "deaths", default=0)
        player.assists = _int_field(rp, "player_assists", "assists", default=0)

        players.append(player)

    return players


def _int_field(data: Dict[str, Any], *keys: str, default: int = 0) -> int:
    """Return the first present key coerced to int, else *default*."""
    for key in keys:
        if key not in data or data[key] is None:
            continue
        try:
            return int(data[key])
        except (TypeError, ValueError):
            continue
    return default
