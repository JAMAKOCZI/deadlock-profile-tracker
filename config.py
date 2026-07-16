"""Application configuration loaded from environment variables."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# ── .env loading ─────────────────────────────────────────────────────
# Frozen (PyInstaller): prefer exe-adjacent .env with override so CWD
# cannot hijack DEADLOCK_API_BASE_URL / proxies for the published build.
# Source installs: project root first, then CWD.

_PLACEHOLDERS = frozenset({"", "your_steam_api_key_here", "changeme", "xxx"})
_DEFAULT_API = "https://api.deadlock-api.com"
_ALLOWED_API_HOSTS = frozenset(
    {
        "api.deadlock-api.com",
        "localhost",
        "127.0.0.1",
    }
)


def _load_dotenv_files() -> None:
    if getattr(sys, "frozen", False):
        exe_env = Path(sys.executable).resolve().parent / ".env"
        if exe_env.is_file():
            load_dotenv(exe_env, override=True)
        return

    # Source: repo-root .env (next to config.py), then CWD without override
    project_env = Path(__file__).resolve().parent / ".env"
    if project_env.is_file():
        load_dotenv(project_env, override=True)
    load_dotenv(override=False)


_load_dotenv_files()


def _env_str(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


def _env_float(key: str, default: float) -> float:
    raw = os.getenv(key)
    if raw is None or not str(raw).strip():
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("Invalid %s=%r — using default %s", key, raw, default)
        return default


def _env_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("Invalid %s=%r — using default %s", key, raw, default)
        return default


def _normalize_api_base(url: str) -> str:
    url = (url or _DEFAULT_API).strip().rstrip("/")
    if not url:
        return _DEFAULT_API
    parsed = urlparse(url)
    if parsed.scheme not in ("https", "http"):
        logger.warning("Invalid DEADLOCK_API_BASE_URL scheme — using default")
        return _DEFAULT_API
    host = (parsed.hostname or "").lower()
    # Allow http only for localhost (dev)
    if parsed.scheme == "http" and host not in ("localhost", "127.0.0.1"):
        logger.warning(
            "DEADLOCK_API_BASE_URL must use https for non-local hosts — using default"
        )
        return _DEFAULT_API
    if host and host not in _ALLOWED_API_HOSTS:
        # Allow override with explicit opt-in env for power users
        if _env_str("DEADLOCK_API_ALLOW_CUSTOM", "").lower() not in (
            "1",
            "true",
            "yes",
        ):
            logger.warning(
                "DEADLOCK_API_BASE_URL host %r not allowlisted — using default "
                "(set DEADLOCK_API_ALLOW_CUSTOM=1 to override)",
                host,
            )
            return _DEFAULT_API
    return url


# Steam Web API key (optional)
_raw_key = _env_str("STEAM_API_KEY")
STEAM_API_KEY: str = "" if _raw_key.lower() in _PLACEHOLDERS else _raw_key

DEADLOCK_API_BASE_URL: str = _normalize_api_base(
    _env_str("DEADLOCK_API_BASE_URL", _DEFAULT_API)
)

REQUEST_TIMEOUT: float = _env_float("REQUEST_TIMEOUT", 15.0)
DEADLOCK_PATH: str = _env_str("DEADLOCK_PATH")
STEAM_PATH: str = _env_str("STEAM_PATH") or _env_str("STEAM_ROOT")

MAX_ACCOUNT_ATTEMPTS: int = _env_int("MAX_ACCOUNT_ATTEMPTS", 12)
ACCOUNT_RETRY_DELAY_S: float = _env_float("ACCOUNT_RETRY_DELAY_S", 8.0)
MAX_MATCH_LOOKUP_ATTEMPTS: int = _env_int("MAX_MATCH_LOOKUP_ATTEMPTS", 12)
MATCH_LOOKUP_RETRY_DELAY_S: float = _env_float("MATCH_LOOKUP_RETRY_DELAY_S", 4.0)

# Auto-detect wait loop
MAX_AUTO_WAIT_S: float = _env_float("MAX_AUTO_WAIT_S", 600.0)
AUTO_POLL_INTERVAL_S: float = _env_float("AUTO_POLL_INTERVAL_S", 2.0)

# Win-rate enrichment (can be slow for full lobbies)
FETCH_WIN_RATES: bool = _env_str("FETCH_WIN_RATES", "1").lower() not in (
    "0",
    "false",
    "no",
)
WINRATE_SOFT_TIMEOUT_S: float = _env_float("WINRATE_SOFT_TIMEOUT_S", 12.0)

# Steam cache: ignore replay URLs older than this many hours
CACHE_MAX_AGE_HOURS: float = _env_float("CACHE_MAX_AGE_HOURS", 12.0)
CACHE_SCAN_MAX_FILES: int = _env_int("CACHE_SCAN_MAX_FILES", 8000)
