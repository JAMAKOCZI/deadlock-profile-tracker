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
from modules.steam_paths import find_deadlock_install

DEADLOCK_APP_ID = "1422450"
STEAM_URL = f"steam://run/{DEADLOCK_APP_ID}//-condebug/"
# Exact image names for Windows tasklist; short names for pgrep -x
PROCESS_NAMES_WIN = ["project8.exe", "deadlock.exe"]
PROCESS_NAMES_UNIX = ["project8", "deadlock", "citadel"]
CONSOLE_LOG_RELATIVE = Path("game") / "citadel" / "console.log"
TAIL_BYTES = 50 * 1024  # read last 50 KB

MATCH_CREATED_RE = re.compile(
    r"Lobby\s+(\d+)\s+for\s+Match\s+(\d+)\s+created", re.IGNORECASE
)
MATCH_DESTROYED_RE = re.compile(
    r"Lobby\s+(\d+)\s+for\s+Match\s+(\d+)\s+destroyed", re.IGNORECASE
)


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
        for proc in PROCESS_NAMES_UNIX:
            try:
                # Exact process name (-x), not full cmdline (-f)
                result = subprocess.run(
                    ["pgrep", "-x", proc],
                    capture_output=True,
                    timeout=3,
                )
                if result.returncode == 0:
                    return True
            except (OSError, subprocess.SubprocessError):
                continue
        return False

    for proc in PROCESS_NAMES_WIN:
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
        except (OSError, subprocess.SubprocessError):
            continue
    return False


def _find_deadlock_install() -> Optional[Path]:
    """Locate the Deadlock install directory (patchable for tests)."""
    return find_deadlock_install(config.DEADLOCK_PATH)


def get_console_log_path() -> Optional[Path]:
    """Return the path to Deadlock's console.log if it exists."""
    install = _find_deadlock_install()
    if install is None:
        return None
    log = install / CONSOLE_LOG_RELATIVE
    return log if log.exists() else None


def find_match_id_in_console_log() -> Optional[int]:
    """Read console.log and return the match_id of the currently active match."""
    log_path = get_console_log_path()
    if log_path is None:
        return None

    try:
        size = log_path.stat().st_size
        read_start = max(0, size - TAIL_BYTES)
        with open(log_path, "rb") as f:
            if read_start > 0:
                f.seek(read_start)
                f.readline()  # skip partial line
            content_bytes = f.read()
        content = content_bytes.decode("utf-8", errors="replace")
    except OSError:
        return None

    created_matches = list(MATCH_CREATED_RE.finditer(content))
    if not created_matches:
        return None

    last_created = created_matches[-1]
    last_match_id = int(last_created.group(2))
    last_created_pos = last_created.start()

    for m in MATCH_DESTROYED_RE.finditer(content):
        if m.start() > last_created_pos and int(m.group(2)) == last_match_id:
            return None

    return last_match_id
