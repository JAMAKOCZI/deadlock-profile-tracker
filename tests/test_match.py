"""Tests for models/match.py."""

from models.match import Match
from models.player import Player


class TestMatchProperties:
    def _make_match(self, **kwargs):
        defaults = {
            "match_id": 1,
            "players": [
                Player(account_id=i, team=0) for i in range(1, 7)
            ] + [
                Player(account_id=i, team=1) for i in range(7, 13)
            ],
        }
        defaults.update(kwargs)
        return Match(**defaults)

    def test_team_0(self):
        m = self._make_match()
        assert len(m.team_0) == 6
        assert all(p.team == 0 for p in m.team_0)

    def test_team_1(self):
        m = self._make_match()
        assert len(m.team_1) == 6
        assert all(p.team == 1 for p in m.team_1)

    def test_is_active_when_no_winner(self):
        m = self._make_match(winning_team=None)
        assert m.is_active is True

    def test_is_not_active_when_winner(self):
        m = self._make_match(winning_team=0)
        assert m.is_active is False

    def test_empty_match(self):
        m = Match(match_id=0, players=[])
        assert m.team_0 == []
        assert m.team_1 == []
        assert m.is_active is True
