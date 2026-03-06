"""Tests for :mod:`modules.steam_detector`."""

from __future__ import annotations

from modules.steam_detector import SteamUser, parse_loginusers_vdf


class TestParseLoginusersVdf:
    """Tests for the VDF parser."""

    SAMPLE_VDF = '''\
"users"
{
\t"76561198012345678"
\t{
\t\t"AccountName"\t\t"player_one"
\t\t"PersonaName"\t\t"PlayerOne"
\t\t"RememberPassword"\t\t"1"
\t\t"MostRecent"\t\t"1"
\t\t"Timestamp"\t\t"1700000000"
\t}
\t"76561198087654321"
\t{
\t\t"AccountName"\t\t"player_two"
\t\t"PersonaName"\t\t"PlayerTwo"
\t\t"RememberPassword"\t\t"1"
\t\t"MostRecent"\t\t"0"
\t\t"Timestamp"\t\t"1699000000"
\t}
}
'''

    def test_parses_two_users(self) -> None:
        users = parse_loginusers_vdf(self.SAMPLE_VDF)
        assert len(users) == 2

    def test_first_user_fields(self) -> None:
        users = parse_loginusers_vdf(self.SAMPLE_VDF)
        u = users[0]
        assert u.steam_id64 == 76561198012345678
        assert u.persona_name == "PlayerOne"
        assert u.most_recent is True

    def test_second_user_fields(self) -> None:
        users = parse_loginusers_vdf(self.SAMPLE_VDF)
        u = users[1]
        assert u.steam_id64 == 76561198087654321
        assert u.persona_name == "PlayerTwo"
        assert u.most_recent is False

    def test_empty_string_returns_empty(self) -> None:
        assert parse_loginusers_vdf("") == []

    def test_malformed_vdf_returns_empty(self) -> None:
        assert parse_loginusers_vdf("not a vdf file") == []

    def test_single_user_most_recent(self) -> None:
        vdf = '''
"users"
{
    "76561198099999999"
    {
        "PersonaName"   "Solo"
        "MostRecent"    "1"
    }
}
'''
        users = parse_loginusers_vdf(vdf)
        assert len(users) == 1
        assert users[0].steam_id64 == 76561198099999999
        assert users[0].persona_name == "Solo"
        assert users[0].most_recent is True

    def test_user_without_most_recent_defaults_false(self) -> None:
        vdf = '''
"users"
{
    "76561198099999999"
    {
        "PersonaName"   "NoRecent"
    }
}
'''
        users = parse_loginusers_vdf(vdf)
        assert len(users) == 1
        assert users[0].most_recent is False
