"""Detect a Deadlock match ID by scanning Steam's local HTTP cache.

When a player enters the Deadlock loading screen, Steam automatically writes
cache files containing a replay URL like::

    http://replay123.valve.net/1422450/{match_id}/...

This module scans ``Steam/appcache/httpcache/`` recursively, reads up to the
first 200 bytes of each file, and extracts the match ID from any such URL —
without any configuration, admin rights, or ``-condebug`` required.

Ported from the ``scan_cache.rs`` logic in
`deadlock-api/deadlock-api-ingest <https://github.com/deadlock-api/deadlock-api-ingest>`_.
"""

from __future__ import annotations

import os
import platform
from pathlib import Path
from typing import Optional

_DEADLOCK_APP_ID = "1422450"
_VALVE_MARKER = b".valve.net"
_MAX_BYTES = 200
_PATH_END_MARKERS = (b" ", b"'", b"\0", b"\n", b"\r", b'"')


def scan_steam_cache_for_match_id() -> Optional[int]:
    """Scan Steam's local HTTP cache and return the current Deadlock match ID.

    Searches all files under the Steam ``appcache/httpcache/`` directory for a
    cached replay URL that encodes the match ID.  Reads at most
    :data:`_MAX_BYTES` bytes per file so that large cache entries are never
    loaded into memory.

    Returns:
        The match ID as an :class:`int`, or ``None`` if no match was detected.
    """
    try:
        httpcache_dir = _find_httpcache_dir()
        if httpcache_dir is None or not httpcache_dir.is_dir():
            return None

        for filepath in _iter_files(httpcache_dir):
            match_id = _extract_match_id_from_file(filepath)
            if match_id is not None:
                return match_id
    except Exception:  # noqa: BLE001
        return None

    return None


# ── internal helpers ─────────────────────────────────────────────────


def _find_httpcache_dir() -> Optional[Path]:
    """Return the path to Steam's ``appcache/httpcache/`` directory."""
    system = platform.system()

    if system == "Windows":
        candidates = [
            Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
            / "Steam"
            / "appcache"
            / "httpcache",
            Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
            / "Steam"
            / "appcache"
            / "httpcache",
        ]
    elif system == "Darwin":
        home = Path.home()
        candidates = [
            home / "Library" / "Application Support" / "Steam" / "appcache" / "httpcache",
        ]
    else:
        home = Path.home()
        candidates = [
            home / ".steam" / "steam" / "appcache" / "httpcache",
            home / ".local" / "share" / "Steam" / "appcache" / "httpcache",
        ]

    for path in candidates:
        if path.is_dir():
            return path

    return None


def _iter_files(directory: Path):
    """Yield all files under *directory* recursively, skipping ``OSError``."""
    try:
        for entry in os.scandir(directory):
            try:
                if entry.is_dir(follow_symlinks=False):
                    yield from _iter_files(Path(entry.path))
                elif entry.is_file(follow_symlinks=False):
                    yield Path(entry.path)
            except OSError:
                continue
    except OSError:
        return


def _extract_match_id_from_file(filepath: Path) -> Optional[int]:
    """Read up to :data:`_MAX_BYTES` bytes from *filepath* and extract a match ID.

    Args:
        filepath: Path to a single cache file.

    Returns:
        The match ID as an :class:`int`, or ``None`` if not found.
    """
    try:
        with open(filepath, "rb") as fh:
            data = fh.read(_MAX_BYTES)
    except OSError:
        return None

    return _parse_match_id(data)


def _parse_match_id(data: bytes) -> Optional[int]:
    """Extract a Deadlock match ID from raw cache file bytes.

    Searches for the ``b".valve.net"`` marker, reconstructs the host and
    URL path, and parses the match ID from the path segment.

    Args:
        data: Up to :data:`_MAX_BYTES` bytes of cache file content.

    Returns:
        The match ID as an :class:`int`, or ``None`` if not found.
    """
    marker_pos = data.find(_VALVE_MARKER)
    if marker_pos == -1:
        return None

    # Walk backwards from the marker to find the start of the host.
    host_start = marker_pos
    while host_start > 0 and _is_host_char(data[host_start - 1]):
        host_start -= 1

    host_end = marker_pos + len(_VALVE_MARKER)
    host = data[host_start:host_end].decode("ascii", errors="replace")

    if not host.startswith("replay") or ".valve.net" not in host:
        return None

    # Find the first '/' after the host to start the URL path.
    slash_pos = data.find(b"/", host_end)
    if slash_pos == -1:
        return None

    # Find the earliest end marker after the path start.
    path_end = len(data)
    for marker in _PATH_END_MARKERS:
        pos = data.find(marker, slash_pos)
        if pos != -1 and pos < path_end:
            path_end = pos

    path = data[slash_pos:path_end].decode("ascii", errors="replace")

    if _DEADLOCK_APP_ID not in path:
        return None

    # Path format: /{app_id}/{match_id}/...
    parts = path.split("/")
    if len(parts) < 3:
        return None

    try:
        return int(parts[2])
    except ValueError:
        return None


def _is_host_char(byte: int) -> bool:
    """Return ``True`` if *byte* is a valid hostname character (alphanumeric or ``.``)."""
    ch = chr(byte)
    return ch.isascii() and (ch.isalnum() or ch == ".")
