#!/usr/bin/env python3
"""Live smoke test against api.deadlock-api.com.

Exits 0 if core production paths succeed. Requires network.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Allow running from repo root without install
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

from modules.match_finder import (
    find_active_match,
    get_active_matches,
    get_match_by_id,
)
from modules.player_extractor import extract_players
from modules.profile_fetcher import fetch_profiles


async def main() -> int:
    errors: list[str] = []

    async with httpx.AsyncClient() as client:
        active = await get_active_matches(client)
        if not active:
            errors.append("get_active_matches returned empty")
            print("FAIL: no active matches")
            return 1

        print(f"OK  active matches: {len(active)}")
        sample = active[0]
        mid = int(sample["match_id"])
        players = extract_players(sample)
        print(f"OK  extract_players from active: {len(players)} players (match {mid})")
        if len(players) < 2:
            errors.append("active match has <2 players")

        # Live match should resolve via active fallback even if metadata 404s
        by_id = await get_match_by_id(mid, client)
        if by_id is None:
            errors.append(f"get_match_by_id({mid}) failed for live match")
            print(f"FAIL get_match_by_id live {mid}")
        else:
            print(f"OK  get_match_by_id live {mid}")

        aid = players[0].account_id
        found = await find_active_match(aid, client)
        if found is None:
            errors.append(f"find_active_match({aid}) failed for player in active list")
            print(f"FAIL find_active_match {aid}")
        else:
            print(f"OK  find_active_match account {aid} -> match {found.get('match_id')}")

        await fetch_profiles(players[:3], client)
        named = sum(1 for p in players[:3] if p.persona_name)
        print(f"OK  fetch_profiles: {named}/{min(3, len(players))} names filled")
        if named == 0:
            errors.append("fetch_profiles filled no persona names")

        # Finished match via history + metadata
        hist = await client.get(
            f"https://api.deadlock-api.com/v1/players/{aid}/match-history",
            timeout=20,
        )
        if hist.status_code != 200:
            errors.append(f"match-history HTTP {hist.status_code}")
        else:
            rows = hist.json()
            if not rows:
                print("WARN match-history empty")
            else:
                finished_id = int(rows[0]["match_id"])
                meta = await get_match_by_id(finished_id, client)
                if meta is None:
                    # History row may still be in progress / not indexed
                    print(f"WARN metadata not ready for history match {finished_id}")
                else:
                    mplayers = extract_players(meta)
                    kda_ok = any(p.kills or p.deaths or p.assists for p in mplayers)
                    print(
                        f"OK  finished match {finished_id}: "
                        f"{len(mplayers)} players, kda_populated={kda_ok}"
                    )
                    if len(mplayers) < 2:
                        errors.append("metadata roster too small")

    if errors:
        print("SMOKE FAILED:")
        for e in errors:
            print(" -", e)
        return 1

    print("SMOKE PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
