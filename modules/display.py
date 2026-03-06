"""Terminal display for match & player data using *rich*."""

from __future__ import annotations

from typing import List

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from models.match import Match
from models.player import Player

console = Console()


def display_match(match: Match) -> None:
    """Render the match overview and both teams to the terminal."""
    _print_header(match)
    _print_team_table("Team 0 (Amber)", match.team_0, match.net_worth_team_0)
    console.print()
    _print_team_table("Team 1 (Sapphire)", match.team_1, match.net_worth_team_1)
    _print_footer(match)


# ── private helpers ──────────────────────────────────────────────────


def _print_header(match: Match) -> None:
    status = "[green]LIVE[/green]" if match.is_active else "[red]FINISHED[/red]"
    duration = _format_duration(match.duration_s)
    header = (
        f"Match [bold]{match.match_id}[/bold]  •  {status}  •  "
        f"Duration: {duration}  •  Mode: {match.game_mode or 'N/A'}  •  "
        f"Region: {match.region or 'N/A'}  •  "
        f"Spectators: {match.spectators}"
    )
    console.print(Panel(header, title="Deadlock Match", border_style="cyan"))


def _print_team_table(title: str, players: List[Player], net_worth: int) -> None:
    table = Table(title=f"{title}  (Net Worth: {net_worth:,})", show_lines=True)

    table.add_column("#", style="dim", width=3)
    table.add_column("Player", min_width=18)
    table.add_column("Hero ID", justify="center", width=8)
    table.add_column("KDA", justify="center", width=12)
    table.add_column("Win Rate", justify="center", width=10)
    table.add_column("Country", justify="center", width=8)

    for idx, p in enumerate(players, start=1):
        name = p.display_name
        if p.abandoned:
            name = f"[strikethrough]{name}[/strikethrough] [red](left)[/red]"
        win_rate = f"{p.win_rate:.1f}%" if (p.wins + p.losses) > 0 else "N/A"
        table.add_row(
            str(idx),
            name,
            str(p.hero_id) if p.hero_id else "-",
            p.kda_str,
            win_rate,
            p.country_code or "-",
        )

    console.print(table)


def _print_footer(match: Match) -> None:
    if match.winning_team is not None:
        console.print(
            f"\n[bold]Winner:[/bold] Team {match.winning_team}",
            style="green",
        )


def _format_duration(seconds: int) -> str:
    """Return ``MM:SS`` representation."""
    m, s = divmod(seconds, 60)
    return f"{m}:{s:02d}"
