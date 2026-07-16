"""Deadlock Profile Tracker — entry point.

When run without arguments the app auto-detects the locally logged-in
Steam user and waits for a match via console.log and/or Steam HTTP cache.

Usage examples::

    # Auto-detect the local Steam user (default):
    python main.py

    # Look up a player's active/recent match by SteamID3 (account_id):
    python main.py --account-id 123456789

    # Look up a specific match by match_id:
    python main.py --match-id 9876543210

    # Browse currently active (top-200 watched) matches:
    python main.py --active
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from typing import Any, Dict, Optional

import httpx

import config
from models.match import Match
from modules.console_log_detector import (
    find_match_id_in_console_log,
    get_console_log_path,
    is_deadlock_running,
    launch_with_condebug,
)
from modules.display import display_match
from modules.hero_resolver import load_hero_names
from modules.match_finder import (
    find_active_match,
    find_live_match_for_account,
    get_active_matches,
    get_match_by_id,
)
from modules.player_extractor import extract_players
from modules.profile_fetcher import fetch_profiles
from modules.steam_cache_detector import scan_steam_cache_for_match_id
from modules.steam_detector import detect_steam_user
from modules.steamid_converter import steam_id64_to_account_id
from rich.console import Console
from rich.panel import Panel

console = Console()
logger = logging.getLogger("deadlock_tracker")


# ── core workflows ──────────────────────────────────────────────────


async def run_auto_detect() -> None:
    """Auto-detect the local Steam user and wait for a match."""
    console.print(
        Panel(
            "[bold cyan]Deadlock Profile Tracker[/bold cyan]\n"
            "Detecting your Steam account…",
            border_style="cyan",
        )
    )

    user = detect_steam_user()
    if user is None:
        console.print("[red]Could not detect a logged-in Steam account.[/red]")
        console.print(
            "[dim]Tip: use --account-id <SteamID3> or --match-id <id> instead.[/dim]"
        )
        _wait_for_exit()
        return

    try:
        account_id = steam_id64_to_account_id(user.steam_id64)
    except ValueError:
        console.print("[red]Detected Steam account has an invalid SteamID64.[/red]")
        _wait_for_exit()
        return

    console.print(
        f"[green]Detected Steam user:[/green] [bold]{user.persona_name}[/bold] "
        f"(account_id={account_id})\n"
    )

    # Ensure console.log path if possible (optional — cache scan still works)
    await _ensure_console_log()

    console.print(
        "[cyan]Waiting for match…[/cyan] "
        "[dim](Steam cache + console.log + active API)[/dim]"
    )
    elapsed = 0
    match_id: Optional[int] = None
    while True:
        match_id = _detect_local_match_id()
        if match_id is not None:
            break

        # While waiting, poll active list only (cheap, no history hammering)
        async with httpx.AsyncClient() as client:
            match_data = await find_live_match_for_account(account_id, client)
            if match_data is not None:
                console.print(
                    f"[green]Match found via API: {match_data.get('match_id')}[/green]"
                )
                match = _build_match(match_data)
                await _enrich_and_display(match, client)
                _wait_for_exit()
                return

        await asyncio.sleep(2)
        elapsed += 2
        if elapsed % 10 == 0:
            console.print(f"[dim]Still waiting… ({elapsed}s)[/dim]")

    console.print(f"[green]Match detected: {match_id}[/green]")
    await run_for_match_id(match_id, fallback_account_id=account_id)
    _wait_for_exit()


def _detect_local_match_id() -> Optional[int]:
    """Try Steam HTTP cache first, then console.log."""
    match_id = scan_steam_cache_for_match_id()
    if match_id is not None:
        return match_id
    return find_match_id_in_console_log()


async def _ensure_console_log() -> None:
    """Optionally launch Deadlock with -condebug if no log and no game yet."""
    log_path = get_console_log_path()
    if log_path is not None:
        console.print(f"[dim]console.log: {log_path}[/dim]")
        return

    # Cache scan does not need -condebug; only offer relaunch if game is up
    # without condebug and cache is empty.
    if is_deadlock_running():
        console.print(
            "[yellow]Deadlock is running. Match detection uses Steam cache "
            "and/or console.log (-condebug).[/yellow]\n"
            "[dim]If detection fails, close Deadlock and press Enter to "
            "relaunch with -condebug.[/dim]"
        )
        # Non-blocking preference: do not force input if user already has cache
        return

    console.print(
        "[dim]Deadlock not detected. Launching with -condebug for console.log…[/dim]"
    )
    launch_with_condebug()
    console.print("[yellow]Waiting for Deadlock to start…[/yellow]")
    for _ in range(60):
        await asyncio.sleep(2)
        if is_deadlock_running():
            break
    else:
        console.print(
            "[yellow]Deadlock did not start in time — will still poll "
            "Steam cache and API.[/yellow]"
        )
        return

    console.print("[yellow]Waiting for console.log…[/yellow]")
    for _ in range(30):
        await asyncio.sleep(2)
        if get_console_log_path() is not None:
            console.print("[green]console.log ready.[/green]")
            return
    console.print(
        "[dim]console.log not found yet — Steam cache + API still available.[/dim]"
    )


async def run_for_account(account_id: int) -> None:
    """Find a match for *account_id* and display player profiles."""
    max_attempts = config.MAX_ACCOUNT_ATTEMPTS
    delay = config.ACCOUNT_RETRY_DELAY_S

    async with httpx.AsyncClient() as client:
        for attempt in range(1, max_attempts + 1):
            console.print(
                f"[cyan]Searching for match… "
                f"(attempt {attempt}/{max_attempts})[/cyan]"
            )
            match_data = await find_active_match(account_id, client)
            if match_data is not None:
                if match_data.get("_partial_history"):
                    console.print(
                        "[yellow]Only partial history available for this match "
                        "(full roster not indexed yet).[/yellow]"
                    )
                match = _build_match(match_data)
                console.print(
                    f"[green]Found match {match.match_id} — "
                    f"fetching player profiles…[/green]"
                )
                await _enrich_and_display(match, client)
                return

            if attempt < max_attempts:
                console.print(
                    f"[yellow]No match found. Retrying in {delay:.0f}s…[/yellow]"
                )
                await asyncio.sleep(delay)

        console.print(
            "[red]No match found after "
            f"{max_attempts} attempts.[/red]\n"
            "[dim]Player may not be in the top-200 watched active list, "
            "and recent match metadata may not be indexed yet.[/dim]"
        )


async def run_for_match_id(
    match_id: int, fallback_account_id: Optional[int] = None
) -> None:
    """Display player profiles for a specific *match_id*."""
    max_attempts = config.MAX_MATCH_LOOKUP_ATTEMPTS
    delay = config.MATCH_LOOKUP_RETRY_DELAY_S

    async with httpx.AsyncClient() as client:
        match_data: Optional[Dict[str, Any]] = None
        for attempt in range(1, max_attempts + 1):
            console.print(
                f"[cyan]Looking up match_id={match_id}… "
                f"(attempt {attempt}/{max_attempts})[/cyan]"
            )
            match_data = await get_match_by_id(match_id, client)
            if match_data is not None:
                break

            if fallback_account_id is not None:
                by_account = await find_active_match(fallback_account_id, client)
                if by_account is not None and not by_account.get("_partial_history"):
                    match_data = by_account
                    break

            if attempt < max_attempts:
                console.print(
                    f"[yellow]Match not yet available. "
                    f"Retrying in {delay:.0f}s…[/yellow]"
                )
                await asyncio.sleep(delay)

        if match_data is None:
            console.print(
                "[red]Match not found.[/red] "
                "It may not be in the active top-200 list yet, or metadata "
                "is not indexed. Try again after the match ends."
            )
            return

        match = _build_match(match_data)
        console.print("[green]Found match — fetching player profiles…[/green]")
        await _enrich_and_display(match, client)


async def _enrich_and_display(match: Match, client: httpx.AsyncClient) -> None:
    """Load hero names + profiles, then render."""
    hero_names = await load_hero_names(client)
    await fetch_profiles(match.players, client)
    display_match(match, hero_names=hero_names)


async def run_active_list() -> None:
    """Print a summary of currently active matches."""
    async with httpx.AsyncClient() as client:
        console.print("[cyan]Fetching active matches…[/cyan]")
        matches = await get_active_matches(client)
        if not matches:
            console.print(
                "[red]No active matches found "
                "(API error or empty watch list).[/red]"
            )
            return
        console.print(f"[green]Found {len(matches)} active matches.[/green]\n")
        for m in matches[:20]:
            mid = m.get("match_id", "?")
            spectators = m.get("spectators") or 0
            mode = _format_game_mode(
                m.get("game_mode_parsed", m.get("game_mode", "?"))
            ) or "?"
            region = _format_region(
                m.get("region_mode_parsed", m.get("region_mode", "?"))
            ) or "?"
            duration = int(m.get("duration_s") or 0)
            console.print(
                f"  Match [bold]{mid}[/bold]  •  "
                f"Spectators: {spectators}  •  Mode: {mode}  •  "
                f"Region: {region}  •  Duration: {duration // 60}:{duration % 60:02d}"
            )


# ── helpers ──────────────────────────────────────────────────────────


def _build_match(data: dict) -> Match:
    """Construct a :class:`Match` from raw API data."""
    players = extract_players(data)
    winning = data.get("winning_team")
    if winning is None and data.get("match_outcome") is not None:
        # Some payloads only expose outcome as winning team id.
        try:
            winning = int(data["match_outcome"])
        except (TypeError, ValueError):
            winning = None
    else:
        try:
            winning = int(winning) if winning is not None else None
        except (TypeError, ValueError):
            winning = None

    return Match(
        match_id=int(data.get("match_id") or 0),
        lobby_id=int(data.get("lobby_id") or 0),
        start_time=int(data.get("start_time") or 0),
        duration_s=int(data.get("duration_s") or 0),
        game_mode=_format_game_mode(
            data.get("game_mode_parsed", data.get("game_mode", ""))
        ),
        region=_format_region(
            data.get("region_mode_parsed", data.get("region_mode", ""))
        ),
        spectators=int(data.get("spectators") or 0),
        net_worth_team_0=int(data.get("net_worth_team_0") or 0),
        net_worth_team_1=int(data.get("net_worth_team_1") or 0),
        winning_team=winning,
        players=players,
    )


def _format_game_mode(raw: object) -> str:
    """Humanise API game mode strings/ints."""
    if raw is None or raw == "":
        return ""
    text = str(raw)
    prefix = "KECitadelGameMode"
    if text.startswith(prefix):
        return text[len(prefix):] or text
    return text


def _format_region(raw: object) -> str:
    if raw is None or raw == "":
        return ""
    return str(raw)


def _wait_for_exit() -> None:
    """Pause before closing when running as a bundled exe."""
    if getattr(sys, "frozen", False):
        console.print("\n[dim]Press Enter to exit…[/dim]")
        try:
            input()
        except EOFError:
            pass


def main() -> None:
    logging.basicConfig(
        level=logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(
        description=(
            "Deadlock Profile Tracker — view player profiles for an active match."
        )
    )
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument(
        "--account-id",
        type=int,
        help="SteamID3 (account_id) of a player to look up.",
    )
    group.add_argument(
        "--match-id",
        type=int,
        help="Match ID to look up (active list or metadata).",
    )
    group.add_argument(
        "--active",
        action="store_true",
        help="List currently active (top-200 watched) matches.",
    )

    args = parser.parse_args()

    try:
        if args.account_id is not None:
            asyncio.run(run_for_account(args.account_id))
            _wait_for_exit()
        elif args.match_id is not None:
            asyncio.run(run_for_match_id(args.match_id))
            _wait_for_exit()
        elif args.active:
            asyncio.run(run_active_list())
            _wait_for_exit()
        else:
            asyncio.run(run_auto_detect())
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
        sys.exit(130)


if __name__ == "__main__":
    main()
