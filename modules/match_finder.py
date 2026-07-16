"""Find an active (or most recent) match for a given player.

Uses the public Deadlock API (https://api.deadlock-api.com) contracts as of 2026:

* ``GET /v1/matches/active`` — top-200 watched live matches (full roster)
* ``GET /v1/matches/{match_id}/metadata`` — finished/indexed matches
* ``GET /v1/players/{account_id}/match-history`` — per-player history rows
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx

import config


async def find_live_match_for_account(
    account_id: int, client: httpx.AsyncClient
) -> Optional[Dict[str, Any]]:
    """Return a currently active match containing *account_id*, if any.

    Only consults ``/v1/matches/active`` (client-side filter). Suitable for
    tight polling loops without hammering match-history.
    """
    return await _find_in_active_by_account(account_id, client)


async def find_active_match(
    account_id: int, client: httpx.AsyncClient
) -> Optional[Dict[str, Any]]:
    """Try to find a match for a player.

    Strategy:
      1. Fetch active matches and filter client-side for *account_id*
         (server-side ``?account_id=`` is unreliable).
      2. Fallback: most recent ``match_id`` from match-history, then hydrate
         full match via metadata (finished) or active list (if still live).
    """
    match = await find_live_match_for_account(account_id, client)
    if match is not None:
        return match

    return await _try_recent_match(account_id, client)


async def get_active_matches(client: httpx.AsyncClient) -> List[Dict[str, Any]]:
    """Return currently active (top-200 watched) matches, or ``[]`` on error."""
    url = f"{config.DEADLOCK_API_BASE_URL}/v1/matches/active"
    try:
        resp = await client.get(url, timeout=config.REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else []
    except (httpx.HTTPStatusError, httpx.RequestError):
        return []


async def get_match_by_id(
    match_id: int, client: httpx.AsyncClient
) -> Optional[Dict[str, Any]]:
    """Look up a specific match by ID.

    Strategy:
      1. ``/v1/matches/{match_id}/metadata`` — finished / indexed matches.
      2. Scan ``/v1/matches/active`` for a live match with this ID.
    """
    metadata = await _try_metadata_match(match_id, client)
    if metadata is not None:
        return metadata

    return await _find_in_active_by_match_id(match_id, client)


# ── private helpers ──────────────────────────────────────────────────


def _hoist_team_net_worth(merged: Dict[str, Any]) -> None:
    """Fill net_worth_team_* from nested team structures when missing."""
    if merged.get("net_worth_team_0") or merged.get("net_worth_team_1"):
        return
    teams = merged.get("teams")
    if not isinstance(teams, list):
        return
    for idx, team in enumerate(teams[:2]):
        if not isinstance(team, dict):
            continue
        nw = team.get("net_worth")
        if nw is None:
            continue
        key = f"net_worth_team_{idx}"
        if not merged.get(key):
            try:
                merged[key] = int(nw)
            except (TypeError, ValueError):
                pass


def _player_account_ids(match: Dict[str, Any]) -> List[int]:
    """Collect account_ids from a match payload (top-level or match_info)."""
    players = match.get("players")
    if not isinstance(players, list):
        match_info = match.get("match_info")
        if isinstance(match_info, dict):
            players = match_info.get("players") or []
        else:
            players = []
    ids: List[int] = []
    for p in players:
        if not isinstance(p, dict):
            continue
        aid = p.get("account_id")
        if aid is not None:
            try:
                ids.append(int(aid))
            except (TypeError, ValueError):
                continue
    return ids


async def _find_in_active_by_account(
    account_id: int, client: httpx.AsyncClient
) -> Optional[Dict[str, Any]]:
    matches = await get_active_matches(client)
    for match in matches:
        if account_id in _player_account_ids(match):
            return match
    return None


async def _find_in_active_by_match_id(
    match_id: int, client: httpx.AsyncClient
) -> Optional[Dict[str, Any]]:
    matches = await get_active_matches(client)
    for match in matches:
        try:
            if int(match.get("match_id", -1)) == match_id:
                return match
        except (TypeError, ValueError):
            continue
    return None


async def _try_recent_match(
    account_id: int, client: httpx.AsyncClient
) -> Optional[Dict[str, Any]]:
    """Resolve the newest history match_id, then hydrate full match data."""
    url = f"{config.DEADLOCK_API_BASE_URL}/v1/players/{account_id}/match-history"
    try:
        resp = await client.get(url, timeout=config.REQUEST_TIMEOUT)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        matches = resp.json()
        if not isinstance(matches, list) or not matches:
            return None
        first = matches[0]
        if not isinstance(first, dict):
            return None
        match_id = first.get("match_id")
        if match_id is None:
            return None
        match_id_int = int(match_id)
    except (httpx.HTTPStatusError, httpx.RequestError, TypeError, ValueError):
        return None

    # Prefer full roster (metadata or live active list)
    full = await get_match_by_id(match_id_int, client)
    if full is not None:
        return full

    # Last resort: single-player history row is not a full match; wrap it so
    # extractors still produce one player rather than crashing.
    return {
        "match_id": match_id_int,
        "start_time": first.get("start_time", 0),
        "duration_s": first.get("match_duration_s", 0),
        "game_mode": first.get("game_mode", ""),
        "players": [
            {
                "account_id": account_id,
                "team": first.get("player_team", first.get("team", 0)),
                "hero_id": first.get("hero_id", 0),
                "player_kills": first.get("player_kills", 0),
                "player_deaths": first.get("player_deaths", 0),
                "player_assists": first.get("player_assists", 0),
                "abandoned": bool(first.get("team_abandoned", False)),
            }
        ],
        "_partial_history": True,
    }


async def _try_metadata_match(
    match_id: int, client: httpx.AsyncClient
) -> Optional[Dict[str, Any]]:
    """Query ``/v1/matches/{match_id}/metadata`` and normalise to a flat dict."""
    url = f"{config.DEADLOCK_API_BASE_URL}/v1/matches/{match_id}/metadata"
    try:
        resp = await client.get(url, timeout=config.REQUEST_TIMEOUT)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, dict) or not data:
            return None
        match_info = data.get("match_info")
        if isinstance(match_info, dict):
            # Hoist match_info first, then non-nested outer fields.
            outer = {k: v for k, v in data.items() if k != "match_info"}
            merged: Dict[str, Any] = {**match_info, **outer}
            # Never lose nested players to a missing/empty outer players key.
            if not merged.get("players") and match_info.get("players"):
                merged["players"] = match_info["players"]
            if not merged.get("match_id"):
                merged["match_id"] = match_id
            # Hoist common team net-worth fields if only present under teams.
            _hoist_team_net_worth(merged)
            return merged
        if "match_info" in data:
            data = dict(data)
            data.pop("match_info", None)
        if not data.get("match_id"):
            data["match_id"] = match_id
        return data
    except (httpx.HTTPStatusError, httpx.RequestError):
        return None
