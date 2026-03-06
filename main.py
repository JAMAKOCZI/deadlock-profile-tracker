"""Deadlock Profile Tracker — entry point.

When run without arguments the app auto-detects the locally logged-in
Steam user and looks up their current/recent match.

Usage examples::

    # Auto-detect the local Steam user (default):
    python main.py

    # Look up a player's active match by their SteamID3 (account_id):
    python main.py --account-id 123456789

    # Look up a specific active match by match_id:
    python main.py --match-id 9876543210

    # Browse all currently active (top-200) matches:
    python main.py --active
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import httpx

from models.match import Match
from modules.display import display_match
from modules.match_finder import find_active_match, get_active_matches, get_match_by_id
from modules.player_extractor import extract_players
from modules.profile_fetcher import fetch_profiles
from modules.steam_cache_detector import scan_steam_cache_for_match_id
from modules.steam_detector import detect_steam_user
from modules.steamid_converter import steam_id64_to_account_id
from rich.console import Console
from rich.panel import Panel

console = Console()


# ── core workflows ──────────────────────────────────────────────────


async def run_auto_detect() -> None:
    """Auto-detect the local Steam user and look up their match."""
    console.print(
        Panel(
            "[bold cyan]Deadlock Profile Tracker[/bold cyan]\n"
            "Detecting your Steam account…",
            border_style="cyan",
        )
    )

    user = detect_steam_user()
    if user is None:
        console.print(
            "[red]Could not detect a logged-in Steam account.[/red]\n"
            "Make sure Steam is installed and you have logged in at least once.\n"
            "You can also specify a player manually:\n"
            "  [dim]deadlock-tracker --account-id 123456789[/dim]"
        )
        _wait_for_exit()
        return

    try:
        account_id = steam_id64_to_account_id(user.steam_id64)
    except ValueError:
        console.print(
            "[red]Detected Steam account has an invalid SteamID64 and could not be used.[/red]\n"
            "This can happen if your local Steam configuration contains a malformed or test account entry.\n"
            "You can specify a player manually instead:\n"
            "  [dim]deadlock-tracker --account-id 123456789[/dim]"
        )
        _wait_for_exit()
        return

    console.print(
        f"[green]Detected Steam user:[/green] [bold]{user.persona_name}[/bold] "
        f"(account_id={account_id})\n"
    )
    await run_for_account(account_id)
    _wait_for_exit()


async def run_for_account(account_id: int) -> None:
    """Find a match for *account_id* and display the 12 player profiles."""
    async with httpx.AsyncClient() as client:
        attempt = 0
        while True:
            attempt += 1
            console.print(f"[cyan]Searching for match… (attempt {attempt})[/cyan]")

            # Strategy 0: Steam local httpcache (fastest, no API needed)
            match_id_from_cache = await asyncio.to_thread(scan_steam_cache_for_match_id)
            if match_id_from_cache is not None:
                console.print(f"[green]Detected match from Steam cache: {match_id_from_cache}[/green]")
                match_data = await get_match_by_id(match_id_from_cache, client)
                if match_data is not None:
                    break

            # Strategy A + B: API-based detection
            match_data = await find_active_match(account_id, client)
            if match_data is not None:
                break

            console.print(f"[yellow]No match found. Retrying in 15 seconds…[/yellow]")
            await asyncio.sleep(15)

        match = _build_match(match_data)
        console.print(f"[green]Found match {match.match_id} — fetching player profiles…[/green]")
        await fetch_profiles(match.players, client)
        display_match(match)


async def run_for_match_id(match_id: int) -> None:
    """Display player profiles for a specific *match_id*."""
    async with httpx.AsyncClient() as client:
        console.print(f"[cyan]Looking up match_id={match_id}…[/cyan]")
        match_data = await get_match_by_id(match_id, client)
        if match_data is None:
            console.print("[red]Match not found among currently active matches.[/red]")
            return

        match = _build_match(match_data)
        console.print(f"[green]Found match — fetching player profiles…[/green]")
        await fetch_profiles(match.players, client)
        display_match(match)


async def run_active_list() -> None:
    """Print a summary of all currently active matches."""
    async with httpx.AsyncClient() as client:
        console.print("[cyan]Fetching active matches…[/cyan]")
        matches = await get_active_matches(client)
        if not matches:
            console.print("[red]No active matches found.[/red]")
            return
        console.print(f"[green]Found {len(matches)} active matches.[/green]\n")
        for m in matches[:20]:  # Show top 20
            mid = m.get("match_id", "?")
            spectators = m.get("spectators", 0)
            mode = m.get("game_mode_parsed", m.get("game_mode", "?"))
            region = m.get("region_mode_parsed", m.get("region_mode", "?"))
            duration = m.get("duration_s", 0)
            console.print(
                f"  Match [bold]{mid}[/bold]  •  "
                f"Spectators: {spectators}  •  Mode: {mode}  •  "
                f"Region: {region}  •  Duration: {duration // 60}:{duration % 60:02d}"
            )


# ── helpers ──────────────────────────────────────────────────────────


def _build_match(data: dict) -> Match:
    """Construct a :class:`Match` from raw API data."""
    players = extract_players(data)
    return Match(
        match_id=data.get("match_id", 0),
        lobby_id=data.get("lobby_id", 0),
        start_time=data.get("start_time", 0),
        duration_s=data.get("duration_s", 0),
        game_mode=str(data.get("game_mode_parsed", data.get("game_mode", ""))),
        region=str(data.get("region_mode_parsed", data.get("region_mode", ""))),
        spectators=data.get("spectators", 0),
        net_worth_team_0=data.get("net_worth_team_0", 0),
        net_worth_team_1=data.get("net_worth_team_1", 0),
        winning_team=data.get("winning_team"),
        players=players,
    )


def _wait_for_exit() -> None:
    """Pause before closing when running as a bundled exe."""
    if getattr(sys, "frozen", False):
        console.print("\n[dim]Press Enter to exit…[/dim]")
        input()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Deadlock Profile Tracker — view player profiles for an active match."
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
        help="Match ID to look up among active matches.",
    )
    group.add_argument(
        "--active",
        action="store_true",
        help="List currently active (top-200) matches.",
    )

    args = parser.parse_args()

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
        # Default: auto-detect the local Steam user
        asyncio.run(run_auto_detect())


if __name__ == "__main__":
    main()
