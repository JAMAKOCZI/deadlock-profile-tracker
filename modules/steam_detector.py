"""Auto-detect the currently logged-in Steam user from local Steam client files.

On Windows the Steam client stores login information in::

    C:\\Program Files (x86)\\Steam\\config\\loginusers.vdf

This module reads that file, parses the lightweight VDF (Valve Data Format),
and returns the most recently logged-in user's SteamID64 and persona name.
"""

from __future__ import annotations

import os
import platform
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class SteamUser:
    """A Steam user detected from local client configuration."""

    steam_id64: int
    persona_name: str
    most_recent: bool = False


def detect_steam_user() -> Optional[SteamUser]:
    """Return the most recently logged-in Steam user, or ``None``.

    The function inspects the Steam client's ``loginusers.vdf`` on the
    local machine. If no Steam installation is found or the file cannot
    be parsed, ``None`` is returned.
    """
    vdf_path = _find_loginusers_vdf()
    if vdf_path is None or not vdf_path.is_file():
        return None

    try:
        text = vdf_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    users = parse_loginusers_vdf(text)
    if not users:
        return None

    # Prefer the user flagged as MostRecent
    for u in users:
        if u.most_recent:
            return u

    # Fallback: return the first user found
    return users[0]


def detect_all_steam_users() -> List[SteamUser]:
    """Return all Steam users found in ``loginusers.vdf``."""
    vdf_path = _find_loginusers_vdf()
    if vdf_path is None or not vdf_path.is_file():
        return []

    try:
        text = vdf_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    return parse_loginusers_vdf(text)


# ── parsing ─────────────────────────────────────────────────────────


def parse_loginusers_vdf(text: str) -> List[SteamUser]:
    """Parse ``loginusers.vdf`` content and return a list of users.

    The VDF format is a nested brace-delimited structure. Each top-level
    key under ``"users"`` is a SteamID64, and the child block contains
    ``"PersonaName"`` and ``"MostRecent"`` keys.

    Args:
        text: The full content of ``loginusers.vdf``.

    Returns:
        A list of :class:`SteamUser` instances.
    """
    users: List[SteamUser] = []

    # Very lightweight parser: find blocks like
    #   "76561198012345678"
    #   {
    #       "PersonaName"   "SomePlayer"
    #       "MostRecent"    "1"
    #       ...
    #   }
    # We use a regex-based approach for robustness.
    block_pattern = re.compile(
        r'"(\d{17})"\s*\{([^}]*)\}',
        re.DOTALL,
    )
    kv_pattern = re.compile(r'"(\w+)"\s+"([^"]*)"')

    for match in block_pattern.finditer(text):
        steam_id64_str = match.group(1)
        block_body = match.group(2)

        try:
            steam_id64 = int(steam_id64_str)
        except ValueError:
            continue

        props: dict[str, str] = {}
        for kv in kv_pattern.finditer(block_body):
            props[kv.group(1).lower()] = kv.group(2)

        persona = props.get("personaname", "")
        most_recent = props.get("mostrecent", "0") == "1"

        users.append(
            SteamUser(
                steam_id64=steam_id64,
                persona_name=persona,
                most_recent=most_recent,
            )
        )

    return users


# ── path discovery ──────────────────────────────────────────────────


def _find_loginusers_vdf() -> Optional[Path]:
    """Locate ``loginusers.vdf`` on the current system."""
    system = platform.system()

    if system == "Windows":
        candidates = [
            Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
            / "Steam"
            / "config"
            / "loginusers.vdf",
            Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
            / "Steam"
            / "config"
            / "loginusers.vdf",
        ]
    elif system == "Darwin":
        home = Path.home()
        candidates = [
            home / "Library" / "Application Support" / "Steam" / "config" / "loginusers.vdf",
        ]
    else:
        home = Path.home()
        candidates = [
            home / ".steam" / "steam" / "config" / "loginusers.vdf",
            home / ".local" / "share" / "Steam" / "config" / "loginusers.vdf",
        ]

    for path in candidates:
        if path.is_file():
            return path

    return None
