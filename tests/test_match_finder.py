"""Tests for modules/match_finder.py — uses httpx mock transport."""

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
    async def test_finds_match_via_metadata_endpoint(self):
        match_data = {
            "match_id": 20,
            "match_info": {"players": [], "game_mode": 2},
        }
        transport = _mock_transport({
            "/v1/matches/20/metadata": (200, match_data),
        })
        async with httpx.AsyncClient(transport=transport, base_url="https://test") as client:
            result = await get_match_by_id(20, client)
        assert result is not None
        assert result["match_id"] == 20
        # match_info fields should be hoisted to top level
        assert result["game_mode"] == 2
        assert "match_info" not in result

    async def test_metadata_response_normalisation(self):
        """Fields from match_info are hoisted to the top level."""
        match_data = {
            "match_id": 30,
            "match_info": {
                "players": [{"account_id": 1, "team": 0}],
                "game_mode": 3,
                "region_mode": 2,
            },
        }
        transport = _mock_transport({
            "/v1/matches/30/metadata": (200, match_data),
        })
        async with httpx.AsyncClient(transport=transport, base_url="https://test") as client:
            result = await get_match_by_id(30, client)
        assert result is not None
        assert result["match_id"] == 30
        assert result["game_mode"] == 3
        assert result["region_mode"] == 2
        assert len(result["players"]) == 1
        assert "match_info" not in result

    async def test_falls_back_to_direct_endpoint(self):
        """Falls back to /v1/matches/{id} when metadata returns 404."""
        match_data = {"match_id": 20, "players": []}
        transport = _mock_transport({
            "/v1/matches/20/metadata": (404, None),
            "/v1/matches/20": (200, match_data),
        })
        async with httpx.AsyncClient(transport=transport, base_url="https://test") as client:
            result = await get_match_by_id(20, client)
        assert result is not None
        assert result["match_id"] == 20

    async def test_returns_none_when_both_endpoints_fail(self):
        transport = _mock_transport({
            "/v1/matches/999/metadata": (404, None),
            "/v1/matches/999": (404, None),
        })
        async with httpx.AsyncClient(transport=transport, base_url="https://test") as client:
            result = await get_match_by_id(999, client)
        assert result is None

    async def test_active_list_not_consulted(self):
        """The active-list endpoint should never be called by get_match_by_id."""
        requests_made = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests_made.append(request.url.path)
            if request.url.path == "/v1/matches/55/metadata":
                return httpx.Response(404)
            if request.url.path == "/v1/matches/55":
                return httpx.Response(404)
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport, base_url="https://test") as client:
            result = await get_match_by_id(55, client)

        assert result is None
        assert "/v1/matches/active" not in requests_made
