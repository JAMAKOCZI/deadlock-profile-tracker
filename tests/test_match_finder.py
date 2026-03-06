"""Tests for modules/match_finder.py — uses httpx mock transport."""

import json

import httpx
import pytest

from modules.match_finder import find_active_match, get_active_matches, get_match_by_id


def _mock_transport(responses: dict):
    """Return an httpx.MockTransport that maps URL paths to responses."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        query = str(request.url.query, "utf-8") if request.url.query else ""
        key = f"{path}?{query}" if query else path
        # Try exact match first, then path-only match
        if key in responses:
            status, body = responses[key]
        elif path in responses:
            status, body = responses[path]
        else:
            return httpx.Response(404)
        return httpx.Response(status, json=body)

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
class TestFindActiveMatch:
    async def test_returns_active_match(self):
        match_data = {"match_id": 42, "players": []}
        transport = _mock_transport({
            "/v1/matches/active?account_id=100": (200, [match_data]),
        })
        async with httpx.AsyncClient(transport=transport, base_url="https://test") as client:
            result = await find_active_match(100, client)
        assert result is not None
        assert result["match_id"] == 42

    async def test_fallback_to_recent_match(self):
        recent = {"match_id": 99, "players": []}
        transport = _mock_transport({
            "/v1/matches/active": (200, []),
            "/v1/players/100/matches": (200, [recent]),
        })
        async with httpx.AsyncClient(transport=transport, base_url="https://test") as client:
            result = await find_active_match(100, client)
        assert result is not None
        assert result["match_id"] == 99

    async def test_returns_none_when_nothing_found(self):
        transport = _mock_transport({
            "/v1/matches/active": (404, None),
            "/v1/players/100/matches": (200, []),
        })
        async with httpx.AsyncClient(transport=transport, base_url="https://test") as client:
            result = await find_active_match(100, client)
        assert result is None


@pytest.mark.asyncio
class TestGetActiveMatches:
    async def test_returns_list(self):
        matches = [{"match_id": 1}, {"match_id": 2}]
        transport = _mock_transport({
            "/v1/matches/active": (200, matches),
        })
        async with httpx.AsyncClient(transport=transport, base_url="https://test") as client:
            result = await get_active_matches(client)
        assert len(result) == 2


@pytest.mark.asyncio
class TestGetMatchById:
    async def test_finds_match(self):
        matches = [{"match_id": 10}, {"match_id": 20}]
        transport = _mock_transport({
            "/v1/matches/active": (200, matches),
        })
        async with httpx.AsyncClient(transport=transport, base_url="https://test") as client:
            result = await get_match_by_id(20, client)
        assert result is not None
        assert result["match_id"] == 20

    async def test_returns_none_for_missing(self):
        matches = [{"match_id": 10}]
        transport = _mock_transport({
            "/v1/matches/active": (200, matches),
        })
        async with httpx.AsyncClient(transport=transport, base_url="https://test") as client:
            result = await get_match_by_id(999, client)
        assert result is None
