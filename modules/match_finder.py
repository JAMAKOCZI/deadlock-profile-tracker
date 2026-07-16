"""Find an active (or most recent) match for a given player.

Uses the public Deadlock API (https://api.deadlock-api.com) contracts as of 2026:

* ``GET /v1/matches/active`` — top-200 watched live matches (full roster)
* ``GET /v1/matches/{match_id}/metadata`` — finished/indexed matches
* ``GET /v1/players/{account_id}/match-history`` — per-player history rows
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx

import config

logger = logging.getLogger(__name__)

_HTTP_SOFT = (httpx.HTTPError, ValueError, TypeError, KeyError)


async def find_live_match_for_account(
    account_id: int, client: httpx.AsyncClient
) -> Optional[Dict[str, Any]]:
    """Return a currently active match containing *account_id*, if any."""
    return await _find_in_active_by_account(account_id, client)


async def find_active_match(
    account_id: int, client: httpx.AsyncClient
) -> Optional[Dict[str, Any]]:
    """Find live match, else recent history hydrated to full match if possible."""
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
    except _HTTP_SOFT as exc:
        logger.debug("get_active_matches failed: %s", type(exc).__name__)
        return []


async def get_match_by_id(
    match_id: int, client: httpx.AsyncClient
) -> Optional[Dict[str, Any]]:
    """Look up match by ID: metadata first, then active list scan."""
    metadata = await _try_metadata_match(match_id, client)
    if metadata is not None:
        return metadata
    return await _find_in_active_by_match_id(match_id, client)


# ── private helpers ──────────────────────────────────────────────────


def _hoist_team_net_worth(merged: Dict[str, Any]) -> None:
    """Fill net_worth_team_* from nested team structures when missing."""
    teams = merged.get("teams")
    if not isinstance(teams, list):
        return
    for idx, team in enumerate(teams[:2]):
        if not isinstance(team, dict):
            continue
        key = f"net_worth_team_{idx}"
        if merged.get(key) is not None:
            continue
        nw = team.get("net_worth")
        if nw is None:
            continue
        try:
            merged[key] = int(nw)
        except (TypeError, ValueError):
            pass


def _player_account_ids(match: Dict[str, Any]) -> List[int]:
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
        if aid is None:
            continue
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


def _newest_history_row(matches: List[Any]) -> Optional[Dict[str, Any]]:
    rows = [r for r in matches if isinstance(r, dict) and r.get("match_id") is not None]
    if not rows:
        return None
    return max(
        rows,
        key=lambda r: (int(r.get("start_time") or 0), int(r.get("match_id") or 0)),
    )


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
        first = _newest_history_row(matches)
        if first is None:
            return None
        match_id_int = int(first["match_id"])
    except _HTTP_SOFT:
        return None

    full = await get_match_by_id(match_id_int, client)
    if full is not None:
        return full

    # Partial single-player history row (last resort)
    winning: Optional[int] = None
    try:
        if first.get("match_result") is not None:
            winning = int(first["match_result"])
    except (TypeError, ValueError):
        winning = None

    return {
        "match_id": match_id_int,
        "start_time": first.get("start_time", 0),
        "duration_s": first.get("match_duration_s", 0),
        "game_mode": first.get("game_mode", ""),
        "winning_team": winning,
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
            outer = {k: v for k, v in data.items() if k != "match_info"}
            merged: Dict[str, Any] = {**match_info, **outer}
            if not merged.get("players") and match_info.get("players"):
                merged["players"] = match_info["players"]
            if not merged.get("match_id"):
                merged["match_id"] = match_id
            _hoist_team_net_worth(merged)
            merged["_from_metadata"] = True
            return merged
        if "match_info" in data:
            data = dict(data)
            data.pop("match_info", None)
        if not data.get("match_id"):
            data["match_id"] = match_id
        data["_from_metadata"] = True
        return data
    except _HTTP_SOFT:
        return None
