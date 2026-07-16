"""Auto-detect the currently logged-in Steam user from local Steam client files."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from modules.steam_paths import find_loginusers_vdf


@dataclass
class SteamUser:
    """A Steam user detected from local client configuration."""

    steam_id64: int
    persona_name: str
    most_recent: bool = False


def detect_steam_user() -> Optional[SteamUser]:
    """Return the most recently logged-in Steam user, or ``None``."""
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

    for u in users:
        if u.most_recent:
            return u

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


def parse_loginusers_vdf(text: str) -> List[SteamUser]:
    """Parse ``loginusers.vdf`` content and return a list of users."""
    users: List[SteamUser] = []

    block_pattern = re.compile(
        r'"(\d{16,17})"\s*\{([^{}]*)\}',
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


def _find_loginusers_vdf() -> Optional[Path]:
    """Locate ``loginusers.vdf`` (patchable for tests)."""
    return find_loginusers_vdf()
