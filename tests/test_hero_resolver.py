"""Tests for modules/hero_resolver.py."""

import httpx
import pytest

from modules import hero_resolver
from modules.hero_resolver import hero_name, load_hero_names


@pytest.fixture(autouse=True)
def _clear_cache():
    hero_resolver.clear_cache()
    yield
    hero_resolver.clear_cache()


@pytest.mark.asyncio
async def test_load_hero_names_from_list():
    payload = [
        {"id": 1, "name": "Infernus"},
        {"id": 2, "name": "Seven"},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/assets/heroes":
            return httpx.Response(200, json=payload)
        return httpx.Response(404)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://test"
    ) as client:
        names = await load_hero_names(client)

    assert names[1] == "Infernus"
    assert names[2] == "Seven"
    assert hero_name(1, names) == "Infernus"
    assert hero_name(99, names) == "99"
    assert hero_name(0, names) == "-"


@pytest.mark.asyncio
async def test_load_hero_names_failure_returns_empty():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://test"
    ) as client:
        names = await load_hero_names(client)
    assert names == {}
