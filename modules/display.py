"""Terminal display for match & player data using *rich*."""

from __future__ import annotations

from typing import Dict, List, Optional

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from models.match import Match
from models.player import Player
from modules.hero_resolver import hero_name

console = Console()


def display_match(
    match: Match, hero_names: Optional[Dict[int, str]] = None
) -> None:
    """Render the match overview and both teams to the terminal."""
    _print_header(match)
    if match.is_partial:
        console.print(
            Panel(
                "[yellow]PARTIAL DATA[/yellow] — only your (or one) player's "
                "history row is available. Full lobby roster is not indexed yet.\n"
                "Re-run after the match ends, or when the match appears in the "
                "active watch list.",
                border_style="yellow",
                title="Limited roster",
            )
        )
    _print_team_table(
        "Team 0 (Amber)", match.team_0, match.net_worth_team_0, hero_names, match
    )
    console.print()
    _print_team_table(
        "Team 1 (Sapphire)", match.team_1, match.net_worth_team_1, hero_names, match
    )
    _print_footer(match)


def _print_header(match: Match) -> None:
    if match.is_partial:
        status = "[yellow]PARTIAL[/yellow]"
    elif match.is_active:
        status = "[green]LIVE[/green]"
    else:
        status = "[red]FINISHED[/red]"
    duration = _format_duration(match.duration_s)
    header = (
        f"Match [bold]{escape(str(match.match_id))}[/bold]  •  {status}  •  "
        f"Duration: {escape(duration)}  •  "
        f"Mode: {escape(match.game_mode or 'N/A')}  •  "
        f"Region: {escape(match.region or 'N/A')}  •  "
        f"Spectators: {match.spectators}"
    )
    console.print(Panel(header, title="Deadlock Match", border_style="cyan"))


def _print_team_table(
    title: str,
    players: List[Player],
    net_worth: int,
    hero_names: Optional[Dict[int, str]] = None,
    match: Optional[Match] = None,
) -> None:
    table = Table(title=f"{title}  (Net Worth: {net_worth:,})", show_lines=True)

    table.add_column("#", style="dim", width=3)
    table.add_column("Player", min_width=18)
    table.add_column("Hero", justify="center", min_width=10)
    table.add_column("KDA", justify="center", width=12)
    table.add_column("Win Rate", justify="center", width=10)
    table.add_column("Country", justify="center", width=8)

    for idx, p in enumerate(players, start=1):
        name = escape(p.display_name)
        if p.abandoned:
            name = f"[strikethrough]{name}[/strikethrough] [red](left)[/red]"
        win_rate = (
            f"{p.win_rate:.1f}%" if (p.wins + p.losses) > 0 else "N/A"
        )
        if p.stats_present:
            kda = p.kda_str
        else:
            kda = "—"
        table.add_row(
            str(idx),
            name,
            escape(hero_name(p.hero_id, hero_names)),
            kda,
            win_rate,
            escape(p.country_code or "-"),
        )

    console.print(table)


def _print_footer(match: Match) -> None:
    if match.winning_team is not None:
        console.print(
            f"\n[bold]Winner:[/bold] Team {escape(str(match.winning_team))}",
            style="green",
        )


def _format_duration(seconds: int) -> str:
    """Return duration as M:SS or H:MM:SS for long matches."""
    total = max(0, int(seconds or 0))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"
