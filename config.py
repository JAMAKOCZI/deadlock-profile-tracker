"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load .env from CWD, and when frozen (PyInstaller) also from the exe directory.
load_dotenv()
if getattr(sys, "frozen", False):
    exe_env = Path(sys.executable).resolve().parent / ".env"
    if exe_env.is_file():
        load_dotenv(exe_env, override=False)

# Steam Web API key (optional — used for enriched Steam profile data)
_raw_key = os.getenv("STEAM_API_KEY", "").strip()
_PLACEHOLDERS = {"", "your_steam_api_key_here", "changeme", "xxx"}
STEAM_API_KEY: str = "" if _raw_key.lower() in _PLACEHOLDERS else _raw_key

# Deadlock API base URL (public, no auth required)
DEADLOCK_API_BASE_URL: str = os.getenv(
    "DEADLOCK_API_BASE_URL", "https://api.deadlock-api.com"
).rstrip("/")

# HTTP request timeout in seconds
REQUEST_TIMEOUT: float = float(os.getenv("REQUEST_TIMEOUT", "15.0"))

# Optional: override Deadlock install path (auto-detected if empty)
DEADLOCK_PATH: str = os.getenv("DEADLOCK_PATH", "")

# Retry policy for account/match polling
MAX_ACCOUNT_ATTEMPTS: int = int(os.getenv("MAX_ACCOUNT_ATTEMPTS", "20"))
ACCOUNT_RETRY_DELAY_S: float = float(os.getenv("ACCOUNT_RETRY_DELAY_S", "15"))
MAX_MATCH_LOOKUP_ATTEMPTS: int = int(os.getenv("MAX_MATCH_LOOKUP_ATTEMPTS", "8"))
MATCH_LOOKUP_RETRY_DELAY_S: float = float(
    os.getenv("MATCH_LOOKUP_RETRY_DELAY_S", "5")
)
