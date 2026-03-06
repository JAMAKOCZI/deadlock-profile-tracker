"""Application configuration loaded from environment variables."""

import os

from dotenv import load_dotenv

load_dotenv()

# Steam Web API key (optional — used for enriched Steam profile data)
STEAM_API_KEY: str = os.getenv("STEAM_API_KEY", "")

# Deadlock API base URL (public, no auth required)
DEADLOCK_API_BASE_URL: str = "https://api.deadlock-api.com"

# HTTP request timeout in seconds
REQUEST_TIMEOUT: float = 15.0

# Optional: override Deadlock install path (auto-detected if empty)
DEADLOCK_PATH: str = os.getenv("DEADLOCK_PATH", "")
