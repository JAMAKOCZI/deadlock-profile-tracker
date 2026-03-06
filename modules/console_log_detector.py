"""Detect current Deadlock match ID from console.log (-condebug)."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Optional

import config

DEADLOCK_APP_ID = "1422450"
STEAM_URL = f"steam://run/{DEADLOCK_APP_ID}//-condebug/"
PROCESS_NAMES = ["project8.exe", "deadlock.exe", "project8"]
CONSOLE_LOG_RELATIVE = Path("game") / "citadel" / "console.log"
TAIL_BYTES = 50 * 1024  # read last 50 KB

MATCH_CREATED_RE = re.compile(r"Lobby\s+(\d+)\s+for\s+Match\s+(\d+)\s+created", re.IGNORECASE)
MATCH_DESTROYED_RE = re.compile(r"Lobby\s+(\d+)\s+for\s+Match\s+(\d+)\s+destroyed", re.IGNORECASE)


def launch_with_condebug() -> None:
    """Launch Deadlock with -condebug via Steam protocol URL."""
    if sys.platform == "win32":
        os.startfile(STEAM_URL)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", STEAM_URL])
    else:
        try:
            subprocess.Popen(["xdg-open", STEAM_URL])
        except FileNotFoundError:
            webbrowser.open(STEAM_URL)


def is_deadlock_running() -> bool:
    """Return True if a Deadlock process is currently running."""
    if os.name != "nt":
        for proc in PROCESS_NAMES:
            try:
                result = subprocess.run(["pgrep", "-f", proc], capture_output=True, timeout=3)
                if result.returncode == 0:
                    return True
            except Exception:
                continue
        return False
    for proc in PROCESS_NAMES:
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {proc}", "/NH"],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if proc.lower() in result.stdout.lower():
                return True
        except Exception:
            continue
    return False


def _find_deadlock_install() -> Optional[Path]:
    """Try to locate the Deadlock install directory."""
    # 1. Env override
    if config.DEADLOCK_PATH:
        p = Path(config.DEADLOCK_PATH).resolve()
        if p.is_dir():
            return p

    # 2. Scan libraryfolders.vdf
    steam_roots = [
        Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)")) / "Steam",
        Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Steam",
        Path.home() / ".steam" / "steam",
        Path.home() / ".local" / "share" / "Steam",
        Path.home() / "Library" / "Application Support" / "Steam",
    ]
    library_paths: list[Path] = []
    for steam_root in steam_roots:
        vdf = steam_root / "steamapps" / "libraryfolders.vdf"
        if vdf.exists():
            try:
                content = vdf.read_text(encoding="utf-8", errors="replace")
                for m in re.finditer(r'"path"\s+"([^"]+)"', content):
                    library_paths.append(Path(m.group(1)))
            except OSError:
                pass
        library_paths.append(steam_root)

    for lib in library_paths:
        candidate = lib / "steamapps" / "common" / "Deadlock"
        if candidate.exists():
            return candidate

    return None


def get_console_log_path() -> Optional[Path]:
    """Return the path to Deadlock's console.log if it exists."""
    install = _find_deadlock_install()
    if install is None:
        return None
    log = install / CONSOLE_LOG_RELATIVE
    return log if log.exists() else None


def find_match_id_in_console_log() -> Optional[int]:
    """Read console.log and return the match_id of the currently active match.

    Returns None if:

    - console.log does not exist
    - no match has started yet
    - the last started match has already ended (Lobby X destroyed found after created)
    """
    log_path = get_console_log_path()
    if log_path is None:
        return None

    try:
        size = log_path.stat().st_size
        read_start = max(0, size - TAIL_BYTES)
        with open(log_path, "rb") as f:
            if read_start > 0:
                f.seek(read_start)
                f.readline()  # skip partial line (binary)
            content_bytes = f.read()
        content = content_bytes.decode("utf-8", errors="replace")
    except OSError:
        return None

    # Find ALL created/destroyed events
    created_matches = list(MATCH_CREATED_RE.finditer(content))
    if not created_matches:
        return None

    # Take the last "created" event
    last_created = created_matches[-1]
    last_match_id = int(last_created.group(2))
    last_created_pos = last_created.start()

    # Check if there's a "destroyed" event for this match AFTER the created event
    destroyed_after = False
    for m in MATCH_DESTROYED_RE.finditer(content):
        if m.start() > last_created_pos and int(m.group(2)) == last_match_id:
            destroyed_after = True
            break

    if destroyed_after:
        return None  # match already ended

    return last_match_id
