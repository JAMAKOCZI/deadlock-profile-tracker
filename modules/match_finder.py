"""Find an active (or most recent) match for a given player."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx

import config


async def find_active_match(account_id: int, client: httpx.AsyncClient) -> Optional[Dict[str, Any]]:
    """Try to find an active match for a player.

    Strategy:
      1. Query ``/v1/matches/active?account_id=`` — works when the player
         is in one of the top-200 watched matches.
      2. Fallback: query ``/v1/players/{account_id}/matches`` and return
         the most recent match (regardless of whether it is still live).

    Args:
        account_id: SteamID3 of the player.
        client: An ``httpx.AsyncClient`` to reuse across calls.

    Returns:
        A dict representing the match data, or ``None`` if nothing was
        found.
    """
    # --- Strategy A: active match endpoint with account_id filter ---
    match = await _try_active_match(account_id, client)
    if match is not None:
        return match

    # --- Strategy B: most recent match from player history ---
    return await _try_recent_match(account_id, client)


async def get_active_matches(client: httpx.AsyncClient) -> List[Dict[str, Any]]:
    """Return the full list of currently active (top-200) matches.

    This can be used when the caller already has a ``match_id`` or simply
    wants to browse live matches.
    """
    url = f"{config.DEADLOCK_API_BASE_URL}/v1/matches/active"
    resp = await client.get(url, timeout=config.REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, list) else []


async def get_match_by_id(
    match_id: int, client: httpx.AsyncClient
) -> Optional[Dict[str, Any]]:
    """Look up a specific match by ID.

    Strategy:
      1. Try ``/v1/matches/{match_id}/metadata`` — works for any match (active
         or finished) regardless of the top-200 active list.
      2. Fallback to ``/v1/matches/{match_id}`` — finished-match endpoint for
         backward compatibility.
    """
    metadata = await _try_metadata_match(match_id, client)
    if metadata is not None:
        return metadata

    return await _try_direct_match(match_id, client)


# ── private helpers ──────────────────────────────────────────────────


async def _try_active_match(
    account_id: int, client: httpx.AsyncClient
) -> Optional[Dict[str, Any]]:
    url = f"{config.DEADLOCK_API_BASE_URL}/v1/matches/active"
    params = {"account_id": str(account_id)}
    try:
        resp = await client.get(url, params=params, timeout=config.REQUEST_TIMEOUT)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
        # The endpoint may return a single object or a list
        if isinstance(data, list) and len(data) > 0:
            return data[0]
        if isinstance(data, dict) and data.get("match_id"):
            return data
    except (httpx.HTTPStatusError, httpx.RequestError):
        pass
    return None


async def _try_recent_match(
    account_id: int, client: httpx.AsyncClient
) -> Optional[Dict[str, Any]]:
    url = f"{config.DEADLOCK_API_BASE_URL}/v1/players/{account_id}/matches"
    try:
        resp = await client.get(url, timeout=config.REQUEST_TIMEOUT)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        matches: List[Dict[str, Any]] = resp.json()
        if not matches:
            return None
        # Return the most recent match (first entry, sorted by start_time desc)
        return matches[0]
    except (httpx.HTTPStatusError, httpx.RequestError):
        pass
    return None


async def _try_metadata_match(
    match_id: int, client: httpx.AsyncClient
) -> Optional[Dict[str, Any]]:
    """Query ``/v1/matches/{match_id}/metadata`` for any match (active or finished).

    Normalises the response into the flat structure the rest of the app
    expects by hoisting ``match_info`` fields to the top level.
    """
    url = f"{config.DEADLOCK_API_BASE_URL}/v1/matches/{match_id}/metadata"
    try:
        resp = await client.get(url, timeout=config.REQUEST_TIMEOUT)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, dict) or not data:
            return None
        # Normalise: hoist match_info fields up to the top level.
        # Top-level fields in data (e.g. match_id) take precedence over
        # same-named fields inside match_info.
        match_info = data.get("match_info", {})
        if isinstance(match_info, dict) and match_info:
            merged: Dict[str, Any] = {**match_info, **data}
            merged.pop("match_info", None)
            return merged
        return data
    except (httpx.HTTPStatusError, httpx.RequestError):
        pass
    return None


async def _try_direct_match(
    match_id: int, client: httpx.AsyncClient
) -> Optional[Dict[str, Any]]:
    """Query ``/v1/matches/{match_id}`` directly.

    This endpoint works for any match, not just the top-200 active ones.
    Returns the match dict on success, or ``None`` on 404 / any HTTP error.
    """
    url = f"{config.DEADLOCK_API_BASE_URL}/v1/matches/{match_id}"
    try:
        resp = await client.get(url, timeout=config.REQUEST_TIMEOUT)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and data:
            return data
    except (httpx.HTTPStatusError, httpx.RequestError):
        pass
    return None
