"""Fetch enriched player profiles from the Deadlock API and Steam Web API."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

import httpx

import config
from models.player import Player
from modules.steamid_converter import account_id_to_steam_id64


# ── public API ───────────────────────────────────────────────────────


async def fetch_profiles(
    players: List[Player], client: httpx.AsyncClient
) -> List[Player]:
    """Enrich a list of players with profile data fetched in parallel.

    For each player we fetch:
      * Deadlock API profile (``/v1/players/{account_id}``) — persona
        name, avatar, country.
      * Optionally, Steam Web API data if ``STEAM_API_KEY`` is
        configured.

    Args:
        players: The list of :class:`Player` objects to enrich (they
            are mutated in-place **and** returned).
        client: A shared ``httpx.AsyncClient``.

    Returns:
        The same list of :class:`Player` objects, now with profile
        fields populated.
    """
    tasks = [_enrich_player(p, client) for p in players]
    await asyncio.gather(*tasks, return_exceptions=True)
    return players


# ── private helpers ──────────────────────────────────────────────────


async def _enrich_player(player: Player, client: httpx.AsyncClient) -> None:
    """Fetch and merge profile data for a single player."""
    # 1. Deadlock API profile
    await _fetch_deadlock_profile(player, client)

    # 2. Steam Web API (optional)
    if config.STEAM_API_KEY:
        await _fetch_steam_profile(player, client)


async def _fetch_deadlock_profile(
    player: Player, client: httpx.AsyncClient
) -> None:
    url = f"{config.DEADLOCK_API_BASE_URL}/v1/players/{player.account_id}"
    try:
        resp = await client.get(url, timeout=config.REQUEST_TIMEOUT)
        if resp.status_code == 404:
            return
        resp.raise_for_status()
        data: Dict[str, Any] = resp.json()
        player.persona_name = player.persona_name or data.get("personaname", "")
        player.avatar_url = player.avatar_url or data.get("avatarfull", "") or data.get("avatar", "")
        player.profile_url = player.profile_url or data.get("profileurl", "")
        player.country_code = player.country_code or data.get("countrycode", "")
    except (httpx.HTTPStatusError, httpx.RequestError):
        pass


async def _fetch_steam_profile(
    player: Player, client: httpx.AsyncClient
) -> None:
    steam_id64 = account_id_to_steam_id64(player.account_id)
    url = "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/"
    params = {
        "key": config.STEAM_API_KEY,
        "steamids": str(steam_id64),
    }
    try:
        resp = await client.get(url, params=params, timeout=config.REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        steam_players = data.get("response", {}).get("players", [])
        if not steam_players:
            return
        sp = steam_players[0]
        # Only overwrite if we didn't already get a value from Deadlock API
        player.persona_name = player.persona_name or sp.get("personaname", "")
        player.avatar_url = player.avatar_url or sp.get("avatarfull", "")
        player.profile_url = player.profile_url or sp.get("profileurl", "")
        player.country_code = player.country_code or sp.get("loccountrycode", "")
    except (httpx.HTTPStatusError, httpx.RequestError):
        pass
