"""Tests for modules/player_extractor.py."""

from modules.player_extractor import extract_players


class TestExtractPlayers:
    def test_extracts_all_players(self):
        match_data = {
            "match_id": 1,
            "players": [
                {"account_id": 100, "team": 0, "hero_id": 1},
                {"account_id": 200, "team": 0, "hero_id": 2},
                {"account_id": 300, "team": 1, "hero_id": 3},
            ],
        }
        players = extract_players(match_data)
        assert len(players) == 3
        assert players[0].account_id == 100
        assert players[0].team == 0
        assert players[0].hero_id == 1

    def test_populates_combat_stats(self):
        match_data = {
            "players": [
                {
                    "account_id": 100,
                    "team": 0,
                    "hero_id": 5,
                    "player_kills": 10,
                    "player_deaths": 3,
                    "player_assists": 7,
                },
            ],
        }
        players = extract_players(match_data)
        assert len(players) == 1
        p = players[0]
        assert p.kills == 10
        assert p.deaths == 3
        assert p.assists == 7

    def test_handles_abandoned_flag(self):
        match_data = {
            "players": [
                {"account_id": 100, "team": 0, "abandoned": True},
            ],
        }
        players = extract_players(match_data)
        assert players[0].abandoned is True

    def test_skips_entries_without_account_id(self):
        match_data = {
            "players": [
                {"team": 0, "hero_id": 1},  # missing account_id
                {"account_id": 200, "team": 1},
            ],
        }
        players = extract_players(match_data)
        assert len(players) == 1
        assert players[0].account_id == 200

    def test_empty_players_list(self):
        assert extract_players({"players": []}) == []

    def test_missing_players_key(self):
        assert extract_players({"match_id": 123}) == []

    def test_players_from_match_info_fallback(self):
        """extract_players should fall back to match_info.players."""
        match_data = {
            "match_id": 999,
            "match_info": {
                "players": [
                    {"account_id": 101, "team": 0, "hero_id": 5},
                    {"account_id": 202, "team": 1, "hero_id": 6},
                ],
            },
        }
        players = extract_players(match_data)
        assert len(players) == 2
        assert players[0].account_id == 101
        assert players[1].account_id == 202

    def test_top_level_players_takes_precedence_over_match_info(self):
        """Top-level players key should take precedence over match_info.players."""
        match_data = {
            "players": [{"account_id": 1, "team": 0}],
            "match_info": {
                "players": [{"account_id": 999, "team": 1}],
            },
        }
        players = extract_players(match_data)
        assert len(players) == 1
        assert players[0].account_id == 1

    def test_empty_top_level_players_not_replaced_by_match_info(self):
        """An explicit empty top-level players list must NOT fall back to match_info."""
        match_data = {
            "players": [],
            "match_info": {
                "players": [{"account_id": 999, "team": 1}],
            },
        }
        players = extract_players(match_data)
        assert players == []

    def test_non_dict_match_info_returns_empty(self):
        """If match_info is not a dict, extract_players should return empty list."""
        match_data = {"match_id": 1, "match_info": "bad_value"}
        players = extract_players(match_data)
        assert players == []

    def test_full_6v6_match(self):
        team_0 = [{"account_id": i, "team": 0, "hero_id": i} for i in range(1, 7)]
        team_1 = [{"account_id": i, "team": 1, "hero_id": i} for i in range(7, 13)]
        match_data = {"players": team_0 + team_1}
        players = extract_players(match_data)
        assert len(players) == 12
        assert len([p for p in players if p.team == 0]) == 6
        assert len([p for p in players if p.team == 1]) == 6
