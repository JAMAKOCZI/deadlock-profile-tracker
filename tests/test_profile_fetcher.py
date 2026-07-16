"""Tests for modules/profile_fetcher.py — uses httpx mock transport."""

import httpx
import pytest

import config
from models.player import Player
from modules.profile_fetcher import fetch_profiles


def _mock_transport(handler):
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
class TestFetchProfiles:
    async def test_enriches_player_from_steam_batch(self, monkeypatch):
        profiles = [
            {
                "account_id": 100,
                "personaname": "TestUser",
                "avatarfull": "https://example.com/avatar.jpg",
                "profileurl": "https://steamcommunity.com/id/test/",
                "countrycode": "PL",
            }
        ]
        history = [
            {"player_team": 0, "match_result": 0},  # win
            {"player_team": 0, "match_result": 1},  # loss
            {"player_team": 1, "match_result": 1},  # win
        ]

        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path == "/v1/players/steam":
                return httpx.Response(200, json=profiles)
            if path == "/v1/players/100/match-history":
                return httpx.Response(200, json=history)
            return httpx.Response(404)

        players = [Player(account_id=100, team=0)]
        monkeypatch.setattr(config, "STEAM_API_KEY", "")
        async with httpx.AsyncClient(
            transport=_mock_transport(handler), base_url="https://test"
        ) as client:
            result = await fetch_profiles(players, client)

        assert len(result) == 1
        assert result[0].persona_name == "TestUser"
        assert result[0].avatar_url == "https://example.com/avatar.jpg"
        assert result[0].country_code == "PL"
        assert result[0].wins == 2
        assert result[0].losses == 1

    async def test_handles_missing_profiles_gracefully(self, monkeypatch):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404)

        players = [Player(account_id=999, team=1)]
        monkeypatch.setattr(config, "STEAM_API_KEY", "")
        async with httpx.AsyncClient(
            transport=_mock_transport(handler), base_url="https://test"
        ) as client:
            result = await fetch_profiles(players, client)

        assert len(result) == 1
        assert result[0].persona_name == ""

    async def test_batches_multiple_players(self, monkeypatch):
        seen_queries = []

        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path == "/v1/players/steam":
                seen_queries.append(str(request.url.query, "utf-8"))
                return httpx.Response(
                    200,
                    json=[
                        {"account_id": 1, "personaname": "A"},
                        {"account_id": 2, "personaname": "B"},
                    ],
                )
            if path.endswith("/match-history"):
                return httpx.Response(200, json=[])
            return httpx.Response(404)

        players = [Player(account_id=1, team=0), Player(account_id=2, team=1)]
        monkeypatch.setattr(config, "STEAM_API_KEY", "")
        async with httpx.AsyncClient(
            transport=_mock_transport(handler), base_url="https://test"
        ) as client:
            result = await fetch_profiles(players, client)

        assert result[0].persona_name == "A"
        assert result[1].persona_name == "B"
        assert len(seen_queries) == 1
        assert "account_ids=1%2C2" in seen_queries[0] or "account_ids=1,2" in seen_queries[0]
