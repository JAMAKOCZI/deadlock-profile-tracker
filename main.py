"""Deadlock Profile Tracker — entry point.

When run without arguments the app auto-detects the locally logged-in
Steam user and waits for a match via console.log and/or Steam HTTP cache.
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
from modules.http_client import create_async_client
from modules.match_finder import (
    find_active_match,
    find_live_match_for_account,
    get_active_matches,
    get_match_by_id,
)
from modules.player_extractor import extract_players
from modules.profile_fetcher import fetch_profiles
from modules.steam_cache_detector import scan_steam_cache_for_match_id
from modules.steam_detector import detect_all_steam_users, detect_steam_user
from modules.steam_paths import steam_not_found_hint
from modules.steamid_converter import steam_id64_to_account_id
from rich.console import Console
from rich.panel import Panel

console = Console()
logger = logging.getLogger("deadlock_tracker")

_GAME_MODE_MAP = {
    0: "Unknown",
    1: "Unranked",
    2: "Ranked",
    3: "Tutorial",
    4: "Normal",
    5: "Custom",
}
_REGION_MAP = {
    0: "Unknown",
    1: "Europe",
    2: "SE Asia",
    3: "S America",
    4: "ROW",
    5: "Russia",
    6: "Oceania",
    7: "US East",
    8: "US West",
    9: "S Africa",
    10: "Asia",
}


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

    all_users = detect_all_steam_users()
    user = detect_steam_user()
    if user is None:
        console.print("[red]Could not detect a logged-in Steam account.[/red]")
        console.print(f"[dim]{steam_not_found_hint()}[/dim]")
        console.print(
            "[dim]Or pass --account-id <SteamID3> / --match-id <id>.[/dim]"
        )
        _wait_for_exit()
        return

    if len(all_users) > 1:
        console.print("[dim]Steam accounts on this machine:[/dim]")
        for u in all_users:
            mark = " ← most recent" if u.most_recent else ""
            console.print(f"  • {u.persona_name or u.steam_id64}{mark}")

    try:
        account_id = steam_id64_to_account_id(user.steam_id64)
    except ValueError:
        console.print("[red]Detected Steam account has an invalid SteamID64.[/red]")
        _wait_for_exit()
        return

    console.print(
        f"[green]Using Steam user:[/green] [bold]{user.persona_name}[/bold] "
        f"(account_id={account_id})\n"
        "[dim]Wrong account? Use --account-id explicitly.[/dim]\n"
    )

    await _maybe_setup_console_log()

    max_wait = config.MAX_AUTO_WAIT_S
    interval = config.AUTO_POLL_INTERVAL_S
    console.print(
        f"[cyan]Waiting for match…[/cyan] "
        f"[dim](cache + console.log + API · max {int(max_wait)}s · Ctrl+C to stop)[/dim]"
    )

    elapsed = 0.0
    api_failures = 0
    match_id: Optional[int] = None

    async with create_async_client() as client:
        while elapsed < max_wait:
            match_id = await _detect_local_match_id()
            if match_id is not None:
                break

            try:
                match_data = await find_live_match_for_account(account_id, client)
                api_failures = 0
            except Exception as exc:  # noqa: BLE001 — surface network issues once
                api_failures += 1
                match_data = None
                if api_failures == 1:
                    console.print(
                        f"[yellow]API unreachable ({type(exc).__name__}) — "
                        "still scanning local Steam cache…[/yellow]"
                    )

            if match_data is not None:
                console.print(
                    f"[green]Match found via API: {match_data.get('match_id')}[/green]"
                )
                match = _build_match(match_data)
                await _enrich_and_display(match, client)
                _wait_for_exit()
                return

            await asyncio.sleep(interval)
            elapsed += interval
            if int(elapsed) % 10 < interval:
                console.print(f"[dim]Still waiting… ({int(elapsed)}s)[/dim]")

        if match_id is None:
            console.print(
                f"[red]No match detected within {int(max_wait)}s.[/red]\n"
                "[dim]Tips: enter a match · set STEAM_PATH if Steam is non-default · "
                "launch Deadlock with -condebug · or use --match-id after the game.[/dim]"
            )
            _wait_for_exit()
            return

        console.print(f"[green]Match detected: {match_id}[/green]")
        await run_for_match_id(
            match_id, fallback_account_id=account_id, client=client
        )
    _wait_for_exit()


async def _detect_local_match_id() -> Optional[int]:
    """Steam cache (thread) then console.log."""
    match_id = await asyncio.to_thread(scan_steam_cache_for_match_id)
    if match_id is not None:
        return match_id
    return find_match_id_in_console_log()


async def _maybe_setup_console_log() -> None:
    """Offer optional -condebug launch; never force without consent."""
    log_path = get_console_log_path()
    if log_path is not None:
        console.print(f"[dim]console.log: {log_path}[/dim]")
        return

    if is_deadlock_running():
        console.print(
            "[yellow]Deadlock is running.[/yellow] "
            "Detection uses Steam cache and/or console.log (-condebug).\n"
            "[dim]If nothing is found, restart Deadlock with -condebug "
            "or wait for the active API list.[/dim]"
        )
        return

    console.print(
        "[dim]Deadlock not detected. Press [bold]Enter[/bold] to launch with "
        "-condebug, or type [bold]s[/bold] + Enter to skip (cache/API only).[/dim]"
    )
    try:
        choice = input().strip().lower()
    except EOFError:
        choice = "s"
    if choice in ("", "y", "yes"):
        console.print("[green]Launching Deadlock with -condebug…[/green]")
        launch_with_condebug()
        for _ in range(45):
            await asyncio.sleep(2)
            if is_deadlock_running():
                break
        for _ in range(20):
            await asyncio.sleep(2)
            if get_console_log_path() is not None:
                console.print("[green]console.log ready.[/green]")
                return
        console.print(
            "[dim]console.log not found yet — Steam cache + API still available.[/dim]"
        )
    else:
        console.print("[dim]Skipping launch — using Steam cache + API only.[/dim]")


async def run_for_account(account_id: int) -> None:
    """Find a match for *account_id* and display player profiles."""
    max_attempts = config.MAX_ACCOUNT_ATTEMPTS
    delay = config.ACCOUNT_RETRY_DELAY_S
    consecutive_net_errors = 0

    async with create_async_client() as client:
        for attempt in range(1, max_attempts + 1):
            console.print(
                f"[cyan]Searching for match… "
                f"(attempt {attempt}/{max_attempts})[/cyan]"
            )
            try:
                match_data = await find_active_match(account_id, client)
                consecutive_net_errors = 0
            except Exception as exc:  # noqa: BLE001
                consecutive_net_errors += 1
                console.print(
                    f"[yellow]Request failed: {type(exc).__name__}[/yellow]"
                )
                if consecutive_net_errors >= 3:
                    console.print(
                        "[red]Repeated network failures — aborting.[/red]"
                    )
                    return
                match_data = None

            if match_data is not None:
                if match_data.get("_partial_history"):
                    console.print(
                        "[yellow]Only partial history available "
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
            f"[red]No match found after {max_attempts} attempts.[/red]\n"
            "[dim]Player may be outside the top-200 watched list, "
            "and recent match metadata may not be indexed yet.[/dim]"
        )


async def run_for_match_id(
    match_id: int,
    fallback_account_id: Optional[int] = None,
    client: Optional[httpx.AsyncClient] = None,
) -> None:
    """Display player profiles for a specific *match_id*."""
    max_attempts = config.MAX_MATCH_LOOKUP_ATTEMPTS
    delay = config.MATCH_LOOKUP_RETRY_DELAY_S
    owns_client = client is None

    if owns_client:
        client = create_async_client()

    assert client is not None
    try:
        if owns_client:
            await client.__aenter__()

        match_data: Optional[Dict[str, Any]] = None
        for attempt in range(1, max_attempts + 1):
            console.print(
                f"[cyan]Looking up match_id={match_id}… "
                f"(attempt {attempt}/{max_attempts})[/cyan]"
            )
            # Prefer active list first while live (metadata often 404s mid-game)
            match_data = await get_match_by_id(match_id, client)
            if match_data is not None:
                break

            if fallback_account_id is not None:
                by_account = await find_live_match_for_account(
                    fallback_account_id, client
                )
                if by_account is not None:
                    match_data = by_account
                    break

            if attempt < max_attempts:
                console.print(
                    f"[yellow]Not in active list / metadata not ready yet "
                    f"(common for live games). Retrying in {delay:.0f}s…[/yellow]"
                )
                await asyncio.sleep(delay)

        if match_data is None:
            console.print(
                f"[red]Match {match_id} not found yet.[/red]\n"
                "[dim]Local detection may work before the cloud indexes the lobby. "
                "Try again after the match ends with the same --match-id, "
                "or when it appears under --active.[/dim]"
            )
            return

        match = _build_match(match_data)
        console.print("[green]Found match — fetching player profiles…[/green]")
        await _enrich_and_display(match, client)
    finally:
        if owns_client:
            await client.__aexit__(None, None, None)


async def _enrich_and_display(match: Match, client: httpx.AsyncClient) -> None:
    hero_names = await load_hero_names(client)
    await fetch_profiles(match.players, client)
    display_match(match, hero_names=hero_names)


async def run_active_list() -> None:
    """Print a summary of currently active matches."""
    async with create_async_client() as client:
        console.print("[cyan]Fetching active matches…[/cyan]")
        matches = await get_active_matches(client)
        if not matches:
            console.print(
                "[red]No active matches found "
                "(API error, offline, or empty watch list).[/red]"
            )
            return
        console.print(f"[green]Found {len(matches)} active matches.[/green]\n")
        for m in matches[:20]:
            mid = m.get("match_id", "?")
            spectators = m.get("spectators") or 0
            mode = (
                _format_game_mode(
                    m.get("game_mode_parsed", m.get("game_mode", "?"))
                )
                or "?"
            )
            region = (
                _format_region(
                    m.get("region_mode_parsed", m.get("region_mode", "?"))
                )
                or "?"
            )
            duration = int(m.get("duration_s") or 0)
            console.print(
                f"  Match [bold]{mid}[/bold]  •  "
                f"Spectators: {spectators}  •  Mode: {mode}  •  "
                f"Region: {region}  •  Duration: {_format_duration(duration)}"
            )


# ── helpers ──────────────────────────────────────────────────────────


def _build_match(data: dict) -> Match:
    """Construct a :class:`Match` from raw API data."""
    players = extract_players(data)
    winning = data.get("winning_team")
    if winning is None and data.get("match_outcome") is not None:
        try:
            winning = int(data["match_outcome"])
        except (TypeError, ValueError):
            winning = None
    else:
        try:
            winning = int(winning) if winning is not None else None
        except (TypeError, ValueError):
            winning = None

    match_id = data.get("match_id")
    try:
        match_id_int = int(match_id) if match_id is not None else 0
    except (TypeError, ValueError):
        match_id_int = 0

    return Match(
        match_id=match_id_int,
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
        is_partial=bool(data.get("_partial_history")),
        from_metadata=bool(data.get("_from_metadata")),
    )


def _format_game_mode(raw: object) -> str:
    if raw is None or raw == "":
        return ""
    if isinstance(raw, int) or (isinstance(raw, str) and raw.isdigit()):
        return _GAME_MODE_MAP.get(int(raw), str(raw))
    text = str(raw)
    prefix = "KECitadelGameMode"
    if text.startswith(prefix):
        return text[len(prefix) :] or text
    return text


def _format_region(raw: object) -> str:
    if raw is None or raw == "":
        return ""
    if isinstance(raw, int) or (isinstance(raw, str) and str(raw).isdigit()):
        return _REGION_MAP.get(int(raw), str(raw))
    return str(raw)


def _format_duration(seconds: int) -> str:
    total = max(0, int(seconds or 0))
    m, s = divmod(total, 60)
    return f"{m}:{s:02d}"


def _wait_for_exit() -> None:
    """Pause before closing when running as a bundled exe."""
    if getattr(sys, "frozen", False):
        console.print("\n[dim]Press Enter to exit…[/dim]")
        try:
            input()
        except EOFError:
            pass


def _positive_int(value: str) -> int:
    try:
        iv = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid integer: {value!r}") from exc
    if iv <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return iv


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
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument(
        "--account-id",
        type=_positive_int,
        help="SteamID3 (account_id) of a player to look up.",
    )
    group.add_argument(
        "--match-id",
        type=_positive_int,
        help="Match ID to look up (active list or metadata).",
    )
    group.add_argument(
        "--active",
        action="store_true",
        help="List currently active (top-200 watched) matches.",
    )
    group.add_argument(
        "--version",
        action="store_true",
        help="Print version and exit.",
    )

    args = parser.parse_args()
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.version:
        print("deadlock-profile-tracker 1.0.1")
        return

    exit_code = 0
    try:
        if args.account_id is not None:
            asyncio.run(run_for_account(args.account_id))
        elif args.match_id is not None:
            asyncio.run(run_for_match_id(args.match_id))
        elif args.active:
            asyncio.run(run_active_list())
        else:
            asyncio.run(run_auto_detect())
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
        exit_code = 130
    except Exception as exc:  # noqa: BLE001 — keep frozen window open
        console.print(f"[red]Unexpected error:[/red] {exc}")
        logger.exception("fatal")
        exit_code = 1
    finally:
        if args.account_id is not None or args.match_id is not None or args.active:
            _wait_for_exit()
        # auto-detect already calls _wait_for_exit on its paths; frozen fatal still pauses
        elif exit_code not in (0, 130) and getattr(sys, "frozen", False):
            _wait_for_exit()

    if exit_code:
        sys.exit(exit_code)


if __name__ == "__main__":
    main()
