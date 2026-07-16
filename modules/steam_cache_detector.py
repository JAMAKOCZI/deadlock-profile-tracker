"""Detect a Deadlock match ID by scanning Steam's local HTTP cache.

When a player enters the Deadlock loading screen, Steam writes cache files
containing a replay URL like::

    http://replay123.valve.net/1422450/{match_id}/...

Prefers the **newest** matching file by mtime so stale prior matches are not
returned. Scan is budgeted (max files) for large httpcache trees.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import List, Optional, Tuple

import config
from modules.steam_paths import find_httpcache_dir

_DEADLOCK_APP_ID = "1422450"
_VALVE_MARKER = b".valve.net"
_MAX_BYTES = 200
_PATH_END_MARKERS = (b" ", b"'", b"\0", b"\n", b"\r", b'"')


def scan_steam_cache_for_match_id() -> Optional[int]:
    """Return the most recent Deadlock match ID found in Steam HTTP cache."""
    try:
        httpcache_dir = _find_httpcache_dir()
        if httpcache_dir is None or not httpcache_dir.is_dir():
            return None

        max_age_s = max(0.0, config.CACHE_MAX_AGE_HOURS) * 3600.0
        now = time.time()
        max_files = max(100, config.CACHE_SCAN_MAX_FILES)

        best: Optional[Tuple[float, int]] = None  # (mtime, match_id)
        scanned = 0

        for filepath in _iter_files(httpcache_dir):
            scanned += 1
            if scanned > max_files:
                break
            try:
                mtime = filepath.stat().st_mtime
            except OSError:
                continue
            if max_age_s and (now - mtime) > max_age_s:
                continue
            match_id = _extract_match_id_from_file(filepath)
            if match_id is None:
                continue
            if best is None or mtime >= best[0]:
                # Prefer newer mtime; on tie prefer higher match_id (monotonic-ish)
                if best is None or mtime > best[0] or match_id > best[1]:
                    best = (mtime, match_id)

        return best[1] if best else None
    except OSError:
        return None


# ── internal helpers ─────────────────────────────────────────────────


def _iter_files(directory: Path):
    """Yield files under *directory* recursively, skipping OSError."""
    try:
        for entry in os_scandir_safe(directory):
            try:
                if entry.is_dir(follow_symlinks=False):
                    yield from _iter_files(Path(entry.path))
                elif entry.is_file(follow_symlinks=False):
                    yield Path(entry.path)
            except OSError:
                continue
    except OSError:
        return


def os_scandir_safe(directory: Path):
    import os

    return os.scandir(directory)


def _extract_match_id_from_file(filepath: Path) -> Optional[int]:
    try:
        with open(filepath, "rb") as fh:
            data = fh.read(_MAX_BYTES)
    except OSError:
        return None
    return _parse_match_id(data)


def _parse_match_id(data: bytes) -> Optional[int]:
    """Extract a Deadlock match ID from raw cache file bytes."""
    search_start = 0

    while True:
        marker_pos = data.find(_VALVE_MARKER, search_start)
        if marker_pos == -1:
            return None

        host_start = marker_pos
        while host_start > 0 and _is_host_char(data[host_start - 1]):
            host_start -= 1

        host_end = marker_pos + len(_VALVE_MARKER)
        host = data[host_start:host_end].decode("ascii", errors="replace")

        if not host.startswith("replay") or ".valve.net" not in host:
            search_start = marker_pos + len(_VALVE_MARKER)
            continue

        slash_pos = data.find(b"/", host_end)
        if slash_pos == -1:
            search_start = marker_pos + len(_VALVE_MARKER)
            continue

        path_end = len(data)
        for marker in _PATH_END_MARKERS:
            pos = data.find(marker, slash_pos)
            if pos != -1 and pos < path_end:
                path_end = pos

        path = data[slash_pos:path_end].decode("ascii", errors="replace")
        parts = path.split("/")
        if len(parts) < 3:
            search_start = marker_pos + len(_VALVE_MARKER)
            continue

        if parts[0] != "" or parts[1] != _DEADLOCK_APP_ID:
            search_start = marker_pos + len(_VALVE_MARKER)
            continue

        try:
            return int(parts[2])
        except ValueError:
            search_start = marker_pos + len(_VALVE_MARKER)
            continue


def _is_host_char(byte: int) -> bool:
    ch = chr(byte)
    return ch.isascii() and (ch.isalnum() or ch == ".")


# Re-export parse helper for tests that import private names
__all__ = [
    "scan_steam_cache_for_match_id",
    "_parse_match_id",
    "_extract_match_id_from_file",
    "_is_host_char",
    "_find_httpcache_dir",
]


def _find_httpcache_dir() -> Optional[Path]:
    """Back-compat for tests that patch this name."""
    return find_httpcache_dir()
