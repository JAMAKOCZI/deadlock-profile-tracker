"""Fetch enriched player profiles from the Deadlock API and Steam Web API."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

import httpx

import config
from models.player import Player
from modules.steamid_converter import account_id_to_steam_id64

logger = logging.getLogger(__name__)

_STEAM_BATCH = 100
_WINRATE_HISTORY_LIMIT = 30
_HTTP_SOFT = (httpx.HTTPError, ValueError, TypeError, KeyError)


async def fetch_profiles(
    players: List[Player],
    client: httpx.AsyncClient,
    *,
    fetch_win_rates: Optional[bool] = None,
) -> List[Player]:
    """Enrich players with Steam persona data and optional win-rate estimate."""
    if not players:
        return players

    await _fetch_deadlock_steam_profiles(players, client)

    if config.STEAM_API_KEY:
        await _fetch_steam_web_profiles(players, client)

    do_wr = config.FETCH_WIN_RATES if fetch_win_rates is None else fetch_win_rates
    if do_wr:
        await _fetch_win_rates(players, client)
    return players


async def _fetch_deadlock_steam_profiles(
    players: List[Player], client: httpx.AsyncClient
) -> None:
    ids = [p.account_id for p in players if p.account_id > 0]
    by_id: Dict[int, Dict[str, Any]] = {}

    for chunk in _chunks(ids, _STEAM_BATCH):
        url = f"{config.DEADLOCK_API_BASE_URL}/v1/players/steam"
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
        except _HTTP_SOFT as exc:
            logger.warning(
                "Deadlock steam profiles failed: %s", type(exc).__name__
            )

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


async def _fetch_steam_web_profiles(
    players: List[Player], client: httpx.AsyncClient
) -> None:
    need = [
        p
        for p in players
        if p.account_id > 0 and (not p.persona_name or not p.avatar_url)
    ]
    if not need:
        return

    for chunk in _chunks(need, _STEAM_BATCH):
        steam_ids_list: List[str] = []
        for p in chunk:
            try:
                steam_ids_list.append(str(account_id_to_steam_id64(p.account_id)))
            except ValueError:
                continue
        if not steam_ids_list:
            continue
        steam_ids = ",".join(steam_ids_list)
        url = "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/"
        params = {"key": config.STEAM_API_KEY, "steamids": steam_ids}
        try:
            resp = await client.get(
                url, params=params, timeout=config.REQUEST_TIMEOUT
            )
            if resp.status_code in (401, 403):
                logger.warning(
                    "Steam API key rejected (HTTP %s)", resp.status_code
                )
                return
            if resp.status_code == 429:
                logger.warning("Steam Web API rate limited (429)")
                return
            resp.raise_for_status()
            data = resp.json()
            steam_players = data.get("response", {}).get("players", [])
            by_sid = {
                int(sp["steamid"]): sp
                for sp in steam_players
                if isinstance(sp, dict) and "steamid" in sp
            }
            for player in chunk:
                try:
                    sid = account_id_to_steam_id64(player.account_id)
                except ValueError:
                    continue
                sp = by_sid.get(sid)
                if not sp:
                    continue
                player.persona_name = player.persona_name or sp.get(
                    "personaname", ""
                )
                player.avatar_url = player.avatar_url or sp.get("avatarfull", "")
                player.profile_url = player.profile_url or sp.get("profileurl", "")
                player.country_code = player.country_code or sp.get(
                    "loccountrycode", ""
                )
        except _HTTP_SOFT as exc:
            # Never log full exception — httpx embeds query string (API key)
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status is not None:
                logger.warning("Steam Web API profiles failed: HTTP %s", status)
            else:
                logger.warning(
                    "Steam Web API profiles failed: %s", type(exc).__name__
                )


async def _fetch_win_rates(
    players: List[Player], client: httpx.AsyncClient
) -> None:
    """Best-effort win/loss with soft timeout for the whole phase."""
    if not players:
        return

    sem = asyncio.Semaphore(3)

    async def _bound(player: Player) -> None:
        async with sem:
            await _fetch_one_win_rate(player, client)

    try:
        await asyncio.wait_for(
            asyncio.gather(
                *[_bound(p) for p in players], return_exceptions=True
            ),
            timeout=config.WINRATE_SOFT_TIMEOUT_S,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "Win-rate fetch soft-timeout after %ss", config.WINRATE_SOFT_TIMEOUT_S
        )


async def _fetch_one_win_rate(player: Player, client: httpx.AsyncClient) -> None:
    if player.account_id <= 0:
        return
    url = (
        f"{config.DEADLOCK_API_BASE_URL}/v1/players/"
        f"{player.account_id}/match-history"
    )
    try:
        resp = await client.get(url, timeout=config.REQUEST_TIMEOUT)
        if resp.status_code in (404, 429):
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
    except _HTTP_SOFT:
        return


def _history_row_is_win(row: Dict[str, Any]) -> Optional[bool]:
    player_team = row.get("player_team", row.get("team"))
    match_result = row.get("match_result")
    if player_team is None or match_result is None:
        return None
    try:
        return int(player_team) == int(match_result)
    except (TypeError, ValueError):
        return None


def _chunks(items: List[Any], size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]
