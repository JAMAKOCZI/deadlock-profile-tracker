"""Tests for modules/profile_fetcher.py — uses httpx mock transport."""

import httpx
import pytest

import config
from models.player import Player
from modules.profile_fetcher import fetch_profiles


def _mock_transport(responses: dict):
    """Return an httpx.MockTransport mapping URL path prefixes to responses."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        for key, (status, body) in responses.items():
            if path.startswith(key):
                return httpx.Response(status, json=body)
        return httpx.Response(404)

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
class TestFetchProfiles:
    async def test_enriches_player_from_deadlock_api(self, monkeypatch):
        profile = {
            "personaname": "TestUser",
            "avatarfull": "https://example.com/avatar.jpg",
            "profileurl": "https://steamcommunity.com/id/test/",
            "countrycode": "PL",
        }
        transport = _mock_transport({
            "/v1/players/": (200, profile),
        })
        players = [Player(account_id=100, team=0)]
        monkeypatch.setattr(config, "STEAM_API_KEY", "")
        async with httpx.AsyncClient(transport=transport, base_url="https://test") as client:
            result = await fetch_profiles(players, client)

        assert len(result) == 1
        assert result[0].persona_name == "TestUser"
        assert result[0].avatar_url == "https://example.com/avatar.jpg"
        assert result[0].country_code == "PL"

    async def test_handles_404_gracefully(self, monkeypatch):
        transport = _mock_transport({})  # everything returns 404
        players = [Player(account_id=999, team=1)]
        monkeypatch.setattr(config, "STEAM_API_KEY", "")
        async with httpx.AsyncClient(transport=transport, base_url="https://test") as client:
            result = await fetch_profiles(players, client)

        assert len(result) == 1
        assert result[0].persona_name == ""  # unchanged
