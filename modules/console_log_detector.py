"""Detect a Deadlock match ID by reading the game's local ``console.log`` file.

When Deadlock is launched with the ``-condebug`` flag it writes all console
output to::

    {deadlock_install_path}/game/citadel/console.log

During match-making the game appends a line like::

    Lobby 12345678 for Match 9876543210 created

This module finds that file, tail-reads the last 50 KB, and extracts the
most-recently created (and not yet destroyed) match ID — no external API or
polling required.

Inspired by `Jelloge/Deadlock-Rich-Presence
<https://github.com/Jelloge/Deadlock-Rich-Presence>`_.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Optional

from config import DEADLOCK_PATH

# ── constants ────────────────────────────────────────────────────────

STEAM_RUN_URL = "steam://run/1422450//-condebug/"

_TAIL_BYTES = 50 * 1024  # 50 KB

MATCH_CREATED_RE = re.compile(
    r"Lobby\s+(\d+)\s+for\s+Match\s+(\d+)\s+created", re.IGNORECASE
)
MATCH_DESTROYED_RE = re.compile(
    r"Lobby\s+(\d+)\s+for\s+Match\s+(\d+)\s+destroyed", re.IGNORECASE
)

PROCESS_NAMES = ["project8.exe", "deadlock.exe", "project8"]

_TASKLIST_TIMEOUT_S = 5   # seconds to wait for tasklist on Windows
_PGREP_TIMEOUT_S = 3      # seconds to wait for pgrep on Unix/macOS


# ── public API ───────────────────────────────────────────────────────


def find_match_id_in_console_log() -> Optional[int]:
    """Return the active Deadlock match ID from ``console.log``, or ``None``.

    Reads the last :data:`_TAIL_BYTES` bytes of ``console.log`` and searches
    for the most-recent ``Lobby X for Match Y created`` line.  If a
    corresponding ``Lobby X for Match Y destroyed`` line is found *after* it,
    the match has already ended and ``None`` is returned.

    Returns:
        The match ID as an :class:`int`, or ``None`` if no active match is
        detected.
    """
    log_path = get_console_log_path()
    if log_path is None:
        return None

    try:
        text = _tail_read(log_path)
    except OSError:
        return None

    return _parse_active_match_id(text)


def launch_with_condebug() -> None:
    """Launch Deadlock via Steam with the ``-condebug`` flag.

    Opens the ``steam://run/1422450//-condebug/`` URL using the platform's
    default URL handler so that Steam starts (or restarts) Deadlock with
    console logging enabled.
    """
    if sys.platform == "win32":
        os.startfile(STEAM_RUN_URL)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", STEAM_RUN_URL])
    else:
        try:
            subprocess.Popen(["xdg-open", STEAM_RUN_URL])
        except FileNotFoundError:
            webbrowser.open(STEAM_RUN_URL)


def is_deadlock_running() -> bool:
    """Return ``True`` if a Deadlock process is currently running.

    Checks for :data:`PROCESS_NAMES` using ``tasklist`` on Windows and
    ``pgrep`` on other platforms.
    """
    if os.name == "nt":
        return _check_processes_windows()
    return _check_processes_unix()


def get_console_log_path() -> Optional[Path]:
    """Return the path to Deadlock's ``console.log`` if it exists.

    Search order:

    1. ``DEADLOCK_PATH`` environment variable (via :mod:`config`).
    2. All Steam library folders discovered from ``libraryfolders.vdf``.

    Returns:
        A :class:`~pathlib.Path` pointing to the existing file, or ``None``.
    """
    if DEADLOCK_PATH:
        p = Path(DEADLOCK_PATH) / "game" / "citadel" / "console.log"
        if p.exists():
            return p

    for lib in _find_steam_libraries():
        p = lib / "steamapps" / "common" / "Deadlock" / "game" / "citadel" / "console.log"
        if p.exists():
            return p

    return None


# ── internal helpers ─────────────────────────────────────────────────


def _tail_read(path: Path) -> str:
    """Read the last :data:`_TAIL_BYTES` bytes of *path* as UTF-8 text.

    Args:
        path: Path to the file to read.

    Returns:
        Decoded string content (last 50 KB).

    Raises:
        OSError: If the file cannot be opened or read.
    """
    with open(path, "rb") as fh:
        fh.seek(0, 2)  # seek to end
        size = fh.tell()
        offset = max(0, size - _TAIL_BYTES)
        fh.seek(offset)
        data = fh.read()
    return data.decode("utf-8", errors="replace")


def _parse_active_match_id(text: str) -> Optional[int]:
    """Parse *text* and return the currently active match ID or ``None``.

    Finds the last ``Lobby X for Match Y created`` occurrence, then checks
    whether a matching ``Lobby X for Match Y destroyed`` line appears after
    it.  If the match was destroyed the function returns ``None``.

    Args:
        text: Tail content of ``console.log``.

    Returns:
        The active match ID as an :class:`int`, or ``None``.
    """
    last_created: Optional[re.Match[str]] = None
    last_created_pos: int = -1

    for m in MATCH_CREATED_RE.finditer(text):
        last_created = m
        last_created_pos = m.start()

    if last_created is None:
        return None

    match_id = int(last_created.group(2))

    # Check whether this match was subsequently destroyed.
    tail_after_created = text[last_created_pos:]
    for m in MATCH_DESTROYED_RE.finditer(tail_after_created):
        if int(m.group(2)) == match_id:
            return None  # match already ended

    return match_id


def _find_steam_libraries() -> list[Path]:
    """Return all Steam library paths from ``libraryfolders.vdf``.

    Checks default Steam installation directories on Windows, macOS, and
    Linux, reads ``libraryfolders.vdf`` from each one, and collects every
    path listed under the ``"path"`` key.

    Returns:
        A list of :class:`~pathlib.Path` objects representing Steam library
        roots (not ``steamapps`` sub-directories — the callers append that).
    """
    candidates = [
        Path(os.environ.get("PROGRAMFILES(X86)", r"C:/Program Files (x86)")) / "Steam",
        Path(os.environ.get("PROGRAMFILES", r"C:/Program Files")) / "Steam",
        Path.home() / ".steam" / "steam",
        Path.home() / ".local" / "share" / "Steam",
        Path.home() / "Library" / "Application Support" / "Steam",
    ]
    libraries: list[Path] = []
    for steam_root in candidates:
        vdf_path = steam_root / "steamapps" / "libraryfolders.vdf"
        if not vdf_path.exists():
            continue
        try:
            content = vdf_path.read_text(encoding="utf-8", errors="replace")
            for m in re.finditer(r'"path"\s+"([^"]+)"', content):
                libraries.append(Path(m.group(1)))
        except OSError:
            pass
        libraries.append(steam_root)
    return libraries


def _check_processes_windows() -> bool:
    """Check for Deadlock process names using ``tasklist`` on Windows."""
    for proc in PROCESS_NAMES:
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {proc}", "/NH"],
                capture_output=True,
                text=True,
                timeout=_TASKLIST_TIMEOUT_S,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if proc.lower() in result.stdout.lower():
                return True
        except Exception:
            continue
    return False


def _check_processes_unix() -> bool:
    """Check for Deadlock process names using ``pgrep`` on Unix/macOS."""
    for proc in PROCESS_NAMES:
        try:
            result = subprocess.run(
                ["pgrep", "-f", proc],
                capture_output=True,
                timeout=_PGREP_TIMEOUT_S,
            )
            if result.returncode == 0:
                return True
        except Exception:
            continue
    return False
