"""Discover Steam install root and library folders across platforms.

Order of preference for the Steam *install root* (config, loginusers, httpcache):

1. ``STEAM_PATH`` / ``STEAM_ROOT`` environment variables
2. Windows registry ``HKCU\\Software\\Valve\\Steam\\SteamPath``
3. Well-known default locations (incl. Flatpak / ``~/.steam`` symlinks)
"""

from __future__ import annotations

import os
import platform
import re
from pathlib import Path
from typing import Iterable, List, Optional

_PATH_RE = re.compile(r'"path"\s+"([^"]+)"', re.IGNORECASE)


def get_steam_root() -> Optional[Path]:
    """Return the Steam client install root, or ``None`` if not found."""
    for candidate in _steam_root_candidates():
        if _looks_like_steam_root(candidate):
            return candidate.resolve()
    return None


def iter_steam_library_paths(steam_root: Optional[Path] = None) -> List[Path]:
    """Return library roots from ``libraryfolders.vdf`` plus the install root."""
    root = steam_root or get_steam_root()
    libraries: List[Path] = []
    seen: set[str] = set()

    def _add(p: Path) -> None:
        try:
            key = str(p.resolve())
        except OSError:
            key = str(p)
        if key in seen:
            return
        if p.is_dir():
            seen.add(key)
            libraries.append(p)

    if root is not None:
        _add(root)
        vdf = root / "steamapps" / "libraryfolders.vdf"
        if vdf.is_file():
            for lib in _parse_libraryfolders(vdf):
                _add(lib)

    # Also scan default roots' VDFs if primary root missed libraries
    if not libraries:
        for cand in _steam_root_candidates():
            if not cand.is_dir():
                continue
            _add(cand)
            vdf = cand / "steamapps" / "libraryfolders.vdf"
            if vdf.is_file():
                for lib in _parse_libraryfolders(vdf):
                    _add(lib)

    return libraries


def find_loginusers_vdf() -> Optional[Path]:
    root = get_steam_root()
    if root is None:
        return None
    path = root / "config" / "loginusers.vdf"
    return path if path.is_file() else None


def find_httpcache_dir() -> Optional[Path]:
    root = get_steam_root()
    if root is None:
        return None
    path = root / "appcache" / "httpcache"
    return path if path.is_dir() else None


def find_deadlock_install(override: str = "") -> Optional[Path]:
    """Locate ``steamapps/common/Deadlock`` using library folders."""
    if override:
        p = Path(override).expanduser()
        try:
            p = p.resolve()
        except OSError:
            pass
        if p.is_dir():
            return p

    for lib in iter_steam_library_paths():
        candidate = lib / "steamapps" / "common" / "Deadlock"
        if candidate.is_dir():
            return candidate
    return None


def steam_not_found_hint() -> str:
    return (
        "Steam not found in default locations. "
        "Set STEAM_PATH to your Steam install root "
        "(folder containing steamapps/ and config/), "
        "or set DEADLOCK_PATH to the Deadlock game folder."
    )


# ── internals ────────────────────────────────────────────────────────


def _steam_root_candidates() -> Iterable[Path]:
    env_keys = ("STEAM_PATH", "STEAM_ROOT")
    for key in env_keys:
        val = os.environ.get(key, "").strip()
        if val:
            yield Path(val).expanduser()

    system = platform.system()
    if system == "Windows":
        reg = _windows_steam_path_from_registry()
        if reg is not None:
            yield reg
        pf86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
        pf = os.environ.get("PROGRAMFILES", r"C:\Program Files")
        yield Path(pf86) / "Steam"
        yield Path(pf) / "Steam"
        # Common custom drives
        for letter in "DEFGHI":
            yield Path(f"{letter}:/Steam")
            yield Path(f"{letter}:/Program Files (x86)/Steam")
            yield Path(f"{letter}:/Program Files/Steam")
    elif system == "Darwin":
        home = Path.home()
        yield home / "Library" / "Application Support" / "Steam"
    else:
        home = Path.home()
        # Resolve ~/.steam symlinks (native Steam / Deck)
        for rel in (".steam/steam", ".steam/root", ".local/share/Steam"):
            p = home / rel
            try:
                if p.exists():
                    yield p.resolve()
            except OSError:
                yield p
        # Flatpak
        yield (
            home
            / ".var"
            / "app"
            / "com.valvesoftware.Steam"
            / ".local"
            / "share"
            / "Steam"
        )
        yield (
            home
            / ".var"
            / "app"
            / "com.valvesoftware.Steam"
            / ".steam"
            / "steam"
        )


def _looks_like_steam_root(path: Path) -> bool:
    try:
        if not path.is_dir():
            return False
        # Either config or steamapps is a strong signal
        return (path / "config").is_dir() or (path / "steamapps").is_dir()
    except OSError:
        return False


def _parse_libraryfolders(vdf: Path) -> List[Path]:
    try:
        text = vdf.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    paths: List[Path] = []
    for m in _PATH_RE.finditer(text):
        raw = m.group(1).replace("\\\\", "\\").strip()
        if not raw:
            continue
        paths.append(Path(raw))
    return paths


def _windows_steam_path_from_registry() -> Optional[Path]:
    if platform.system() != "Windows":
        return None
    try:
        import winreg  # type: ignore[import-not-found]
    except ImportError:
        return None
    for hive, sub in (
        (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Valve\Steam"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Valve\Steam"),
    ):
        try:
            with winreg.OpenKey(hive, sub) as key:
                val, _ = winreg.QueryValueEx(key, "SteamPath")
                if val:
                    return Path(str(val))
        except OSError:
            continue
    return None
