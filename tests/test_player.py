"""Tests for models/player.py."""

from models.player import Player


class TestPlayerProperties:
    def test_kda_str(self):
        p = Player(account_id=1, team=0, kills=10, deaths=3, assists=7)
        assert p.kda_str == "10/3/7"

    def test_win_rate_positive(self):
        p = Player(account_id=1, team=0, wins=7, losses=3)
        assert p.win_rate == 70.0

    def test_win_rate_zero_games(self):
        p = Player(account_id=1, team=0)
        assert p.win_rate == 0.0

    def test_win_rate_all_wins(self):
        p = Player(account_id=1, team=0, wins=10, losses=0)
        assert p.win_rate == 100.0

    def test_display_name_with_persona(self):
        p = Player(account_id=1, team=0, persona_name="Alice")
        assert p.display_name == "Alice"

    def test_display_name_fallback(self):
        p = Player(account_id=42, team=0)
        assert p.display_name == "Player_42"

    def test_steam_id64(self):
        p = Player(account_id=1, team=0)
        assert p.steam_id64 == 76561197960265729


class TestPlayerDefaults:
    def test_default_values(self):
        p = Player(account_id=99, team=1)
        assert p.hero_id == 0
        assert p.abandoned is False
        assert p.persona_name == ""
        assert p.kills == 0
        assert p.deaths == 0
        assert p.assists == 0
        assert p.wins == 0
        assert p.losses == 0
