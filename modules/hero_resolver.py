"""Resolve Deadlock hero IDs to display names via the assets API."""

from __future__ import annotations

import logging
import time
from typing import Dict, Optional

import httpx

import config

logger = logging.getLogger(__name__)

_cache: Optional[Dict[int, str]] = None
_cache_failed_at: float = 0.0
_FAIL_RETRY_S = 60.0


async def load_hero_names(client: httpx.AsyncClient) -> Dict[int, str]:
    """Fetch and cache ``hero_id -> name`` mapping."""
    global _cache, _cache_failed_at

    if _cache is not None:
        return _cache

    # Retry after failure cooldown
    if _cache_failed_at and (time.monotonic() - _cache_failed_at) < _FAIL_RETRY_S:
        return {}

    url = f"{config.DEADLOCK_API_BASE_URL}/v1/assets/heroes"
    mapping: Dict[int, str] = {}
    try:
        resp = await client.get(url, timeout=config.REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            for row in data:
                if not isinstance(row, dict):
                    continue
                hid = row.get("id")
                name = row.get("name")
                if hid is not None and name:
                    mapping[int(hid)] = str(name)
        elif isinstance(data, dict):
            for key, row in data.items():
                if isinstance(row, dict):
                    hid = row.get("id", key)
                    name = row.get("name")
                    if name:
                        mapping[int(hid)] = str(name)
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        logger.warning("Failed to load hero assets: %s", type(exc).__name__)
        _cache_failed_at = time.monotonic()
        return {}

    if mapping:
        _cache = mapping
        _cache_failed_at = 0.0
    else:
        _cache_failed_at = time.monotonic()
    return mapping


def hero_name(hero_id: int, names: Optional[Dict[int, str]] = None) -> str:
    """Return a display name for *hero_id*."""
    if not hero_id:
        return "-"
    table = names if names is not None else _cache
    if table and hero_id in table:
        return table[hero_id]
    return str(hero_id)


def clear_cache() -> None:
    """Test helper: reset the module-level cache."""
    global _cache, _cache_failed_at
    _cache = None
    _cache_failed_at = 0.0
