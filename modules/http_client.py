"""Shared httpx client factory for reliable API access."""

from __future__ import annotations

import httpx

import config

USER_AGENT = (
    "deadlock-profile-tracker/1.0 "
    "(+https://github.com/JAMAKOCZI/deadlock-profile-tracker)"
)


def create_async_client() -> httpx.AsyncClient:
    """Create an AsyncClient with safe defaults for this CLI.

    - Explicit User-Agent (community APIs may rate-limit anonymous UAs)
    - Connection limits + keep-alive
    - ``trust_env=False`` so planted HTTP(S)_PROXY cannot siphon Steam keys
    - Default timeout from config
    """
    return httpx.AsyncClient(
        timeout=httpx.Timeout(config.REQUEST_TIMEOUT, connect=10.0),
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        follow_redirects=True,
        trust_env=False,
    )
