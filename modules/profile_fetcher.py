"""Fetch enriched player profiles from the Deadlock API and Steam Web API."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx

import config
from models.player import Player
from modules.steamid_converter import account_id_to_steam_id64

logger = logging.getLogger(__name__)

# Batch size for Deadlock / Steam profile endpoints
_STEAM_BATCH = 100
# How many recent history rows to sample for win-rate estimate
_WINRATE_HISTORY_LIMIT = 50


async def fetch_profiles(
    players: List[Player], client: httpx.AsyncClient
) -> List[Player]:
    """Enrich players with Steam persona data and a win-rate estimate.

    1. Batch ``GET /v1/players/steam?account_ids=…`` (Deadlock API).
    2. Optional Steam Web API batch if ``STEAM_API_KEY`` is set.
    3. Approximate win rate from recent match-history (best-effort).
    """
    if not players:
        return players

    await _fetch_deadlock_steam_profiles(players, client)

    if config.STEAM_API_KEY:
        await _fetch_steam_web_profiles(players, client)

    await _fetch_win_rates(players, client)
    return players


# ── Deadlock steam profiles (batch) ──────────────────────────────────


async def _fetch_deadlock_steam_profiles(
    players: List[Player], client: httpx.AsyncClient
) -> None:
    ids = [p.account_id for p in players]
    by_id: Dict[int, Dict[str, Any]] = {}

    for chunk in _chunks(ids, _STEAM_BATCH):
        url = f"{config.DEADLOCK_API_BASE_URL}/v1/players/steam"
        # OpenAPI: comma-separated account ids (also accepts repeated params)
        params = {"account_ids": ",".join(str(i) for i in chunk)}
        try:
            resp = await client.get(
                url, params=params, timeout=config.REQUEST_TIMEOUT
            )
            if resp.status_code == 404:
                continue
            resp.raise_for_status()
            data = resp.json()
            rows = data if isinstance(data, list) else []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                aid = row.get("account_id")
                if aid is None:
                    continue
                by_id[int(aid)] = row
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            logger.warning("Deadlock steam profiles failed: %s", exc)

    for player in players:
        row = by_id.get(player.account_id)
        if not row:
            continue
        _apply_steam_row(player, row)


def _apply_steam_row(player: Player, row: Dict[str, Any]) -> None:
    player.persona_name = player.persona_name or (row.get("personaname") or "")
    player.avatar_url = (
        player.avatar_url
        or (row.get("avatarfull") or "")
        or (row.get("avatar") or "")
    )
    player.profile_url = player.profile_url or (row.get("profileurl") or "")
    country = row.get("countrycode") or row.get("loccountrycode") or ""
    player.country_code = player.country_code or country


# ── Steam Web API (optional batch) ───────────────────────────────────


async def _fetch_steam_web_profiles(
    players: List[Player], client: httpx.AsyncClient
) -> None:
    """Fill gaps using Steam GetPlayerSummaries (up to 100 steamids per call)."""
    need = [p for p in players if not p.persona_name or not p.avatar_url]
    if not need:
        return

    for chunk in _chunks(need, _STEAM_BATCH):
        steam_ids = ",".join(
            str(account_id_to_steam_id64(p.account_id)) for p in chunk
        )
        url = "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/"
        params = {"key": config.STEAM_API_KEY, "steamids": steam_ids}
        try:
            resp = await client.get(
                url, params=params, timeout=config.REQUEST_TIMEOUT
            )
            if resp.status_code in (401, 403):
                logger.warning("Steam API key rejected (HTTP %s)", resp.status_code)
                return
            resp.raise_for_status()
            data = resp.json()
            steam_players = data.get("response", {}).get("players", [])
            by_sid = {int(sp["steamid"]): sp for sp in steam_players if "steamid" in sp}
            for player in chunk:
                sp = by_sid.get(account_id_to_steam_id64(player.account_id))
                if not sp:
                    continue
                player.persona_name = player.persona_name or sp.get("personaname", "")
                player.avatar_url = player.avatar_url or sp.get("avatarfull", "")
                player.profile_url = player.profile_url or sp.get("profileurl", "")
                player.country_code = player.country_code or sp.get(
                    "loccountrycode", ""
                )
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            logger.warning("Steam Web API profiles failed: %s", exc)


# ── Win rate from match history ──────────────────────────────────────


async def _fetch_win_rates(
    players: List[Player], client: httpx.AsyncClient
) -> None:
    """Best-effort win/loss counts from recent match-history rows."""
    import asyncio

    sem = asyncio.Semaphore(6)

    async def _bound(player: Player) -> None:
        async with sem:
            await _fetch_one_win_rate(player, client)

    await asyncio.gather(*[_bound(p) for p in players], return_exceptions=True)


async def _fetch_one_win_rate(player: Player, client: httpx.AsyncClient) -> None:
    url = (
        f"{config.DEADLOCK_API_BASE_URL}/v1/players/"
        f"{player.account_id}/match-history"
    )
    try:
        resp = await client.get(url, timeout=config.REQUEST_TIMEOUT)
        if resp.status_code == 404:
            return
        resp.raise_for_status()
        rows = resp.json()
        if not isinstance(rows, list):
            return
        wins = 0
        losses = 0
        for row in rows[:_WINRATE_HISTORY_LIMIT]:
            if not isinstance(row, dict):
                continue
            result = _history_row_is_win(row)
            if result is True:
                wins += 1
            elif result is False:
                losses += 1
        player.wins = wins
        player.losses = losses
    except (httpx.HTTPStatusError, httpx.RequestError):
        return


def _history_row_is_win(row: Dict[str, Any]) -> Optional[bool]:
    """Return True/False if outcome is known, else None.

    Deadlock match-history uses ``match_result`` as the winning team id
    (0 or 1) and ``player_team`` as the player's team.
    """
    player_team = row.get("player_team", row.get("team"))
    match_result = row.get("match_result")
    if player_team is None or match_result is None:
        return None
    try:
        return int(player_team) == int(match_result)
    except (TypeError, ValueError):
        return None


# ── utils ────────────────────────────────────────────────────────────


def _chunks(items: List[Any], size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]
