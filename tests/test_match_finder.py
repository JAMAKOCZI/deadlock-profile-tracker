"""Tests for modules/match_finder.py — uses httpx mock transport."""

import httpx
import pytest

from modules.match_finder import (
    find_active_match,
    find_live_match_for_account,
    get_active_matches,
    get_match_by_id,
)


def _mock_transport(responses: dict):
    """Return an httpx.MockTransport that maps URL paths to responses."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        query = str(request.url.query, "utf-8") if request.url.query else ""
        key = f"{path}?{query}" if query else path
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
    async def test_returns_active_match_via_client_filter(self):
        match_data = {
            "match_id": 42,
            "players": [{"account_id": 100, "team": 0, "hero_id": 1}],
        }
        other = {
            "match_id": 41,
            "players": [{"account_id": 999, "team": 0, "hero_id": 2}],
        }
        transport = _mock_transport({
            "/v1/matches/active": (200, [other, match_data]),
        })
        async with httpx.AsyncClient(transport=transport, base_url="https://test") as client:
            result = await find_active_match(100, client)
        assert result is not None
        assert result["match_id"] == 42

    async def test_live_only_skips_history(self):
        transport = _mock_transport({
            "/v1/matches/active": (200, []),
            "/v1/players/100/match-history": (
                200,
                [{"match_id": 99, "player_team": 0, "match_result": 0}],
            ),
        })
        async with httpx.AsyncClient(transport=transport, base_url="https://test") as client:
            result = await find_live_match_for_account(100, client)
        assert result is None

    async def test_fallback_to_recent_match_via_metadata(self):
        history = [{"match_id": 99, "player_team": 0, "player_kills": 1}]
        full = {
            "match_id": 99,
            "match_info": {
                "players": [
                    {"account_id": 100, "team": 0, "kills": 5, "deaths": 1, "assists": 2},
                    {"account_id": 200, "team": 1, "kills": 1, "deaths": 5, "assists": 0},
                ],
                "duration_s": 600,
            },
        }
        transport = _mock_transport({
            "/v1/matches/active": (200, []),
            "/v1/players/100/match-history": (200, history),
            "/v1/matches/99/metadata": (200, full),
        })
        async with httpx.AsyncClient(transport=transport, base_url="https://test") as client:
            result = await find_active_match(100, client)
        assert result is not None
        assert result["match_id"] == 99
        assert len(result["players"]) == 2

    async def test_fallback_partial_when_metadata_missing(self):
        history = [
            {
                "match_id": 77,
                "hero_id": 3,
                "player_team": 1,
                "player_kills": 2,
                "player_deaths": 1,
                "player_assists": 4,
            }
        ]
        transport = _mock_transport({
            "/v1/matches/active": (200, []),
            "/v1/players/100/match-history": (200, history),
            "/v1/matches/77/metadata": (404, None),
        })
        async with httpx.AsyncClient(transport=transport, base_url="https://test") as client:
            result = await find_active_match(100, client)
        assert result is not None
        assert result["match_id"] == 77
        assert result.get("_partial_history") is True
        assert result["players"][0]["account_id"] == 100

    async def test_returns_none_when_nothing_found(self):
        transport = _mock_transport({
            "/v1/matches/active": (200, []),
            "/v1/players/100/match-history": (200, []),
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

    async def test_returns_empty_on_http_error(self):
        transport = _mock_transport({
            "/v1/matches/active": (500, {"error": "boom"}),
        })
        async with httpx.AsyncClient(transport=transport, base_url="https://test") as client:
            result = await get_active_matches(client)
        assert result == []


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
        assert result["game_mode"] == 2
        assert "match_info" not in result

    async def test_metadata_response_normalisation(self):
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

    async def test_falls_back_to_active_list(self):
        """When metadata 404s, scan /v1/matches/active for the match_id."""
        live = {
            "match_id": 20,
            "players": [{"account_id": 1, "team": 0, "hero_id": 5}],
            "duration_s": 120,
        }
        transport = _mock_transport({
            "/v1/matches/20/metadata": (404, None),
            "/v1/matches/active": (200, [live]),
        })
        async with httpx.AsyncClient(transport=transport, base_url="https://test") as client:
            result = await get_match_by_id(20, client)
        assert result is not None
        assert result["match_id"] == 20
        assert result["players"][0]["account_id"] == 1

    async def test_returns_none_when_metadata_and_active_fail(self):
        transport = _mock_transport({
            "/v1/matches/999/metadata": (404, None),
            "/v1/matches/active": (200, []),
        })
        async with httpx.AsyncClient(transport=transport, base_url="https://test") as client:
            result = await get_match_by_id(999, client)
        assert result is None

    async def test_active_list_is_consulted_after_metadata_404(self):
        requests_made = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests_made.append(request.url.path)
            if request.url.path == "/v1/matches/55/metadata":
                return httpx.Response(404)
            if request.url.path == "/v1/matches/active":
                return httpx.Response(200, json=[])
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport, base_url="https://test") as client:
            result = await get_match_by_id(55, client)

        assert result is None
        assert "/v1/matches/active" in requests_made

    async def test_empty_match_info_is_normalised(self):
        match_data = {"match_id": 40, "match_info": {}}
        transport = _mock_transport({
            "/v1/matches/40/metadata": (200, match_data),
        })
        async with httpx.AsyncClient(transport=transport, base_url="https://test") as client:
            result = await get_match_by_id(40, client)
        assert result is not None
        assert result["match_id"] == 40
        assert "match_info" not in result

    async def test_non_dict_match_info_is_dropped(self):
        match_data = {"match_id": 41, "match_info": "unexpected_string"}
        transport = _mock_transport({
            "/v1/matches/41/metadata": (200, match_data),
        })
        async with httpx.AsyncClient(transport=transport, base_url="https://test") as client:
            result = await get_match_by_id(41, client)
        assert result is not None
        assert result["match_id"] == 41
        assert "match_info" not in result
