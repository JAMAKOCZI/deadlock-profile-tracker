"""Tests for :mod:`modules.steam_detector`."""

from __future__ import annotations

from pathlib import Path

from modules.steam_detector import (
    SteamUser,
    detect_all_steam_users,
    detect_steam_user,
    parse_loginusers_vdf,
)


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


class TestParseLoginusersVdf:
    """Tests for the VDF parser."""

    def test_parses_two_users(self) -> None:
        users = parse_loginusers_vdf(SAMPLE_VDF)
        assert len(users) == 2

    def test_first_user_fields(self) -> None:
        users = parse_loginusers_vdf(SAMPLE_VDF)
        u = users[0]
        assert u.steam_id64 == 76561198012345678
        assert u.persona_name == "PlayerOne"
        assert u.most_recent is True

    def test_second_user_fields(self) -> None:
        users = parse_loginusers_vdf(SAMPLE_VDF)
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


class TestDetectSteamUser:
    """Tests for detect_steam_user() using monkeypatch to simulate VDF files."""

    def test_returns_most_recent_user(self, tmp_path: Path, monkeypatch) -> None:
        vdf_file = tmp_path / "loginusers.vdf"
        vdf_file.write_text(SAMPLE_VDF, encoding="utf-8")
        monkeypatch.setattr(
            "modules.steam_detector._find_loginusers_vdf", lambda: vdf_file
        )
        user = detect_steam_user()
        assert user is not None
        assert user.steam_id64 == 76561198012345678
        assert user.persona_name == "PlayerOne"
        assert user.most_recent is True

    def test_fallback_to_first_user_when_no_most_recent(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        vdf = '''
"users"
{
    "76561198012345678"
    {
        "PersonaName"   "Alpha"
        "MostRecent"    "0"
    }
    "76561198087654321"
    {
        "PersonaName"   "Beta"
        "MostRecent"    "0"
    }
}
'''
        vdf_file = tmp_path / "loginusers.vdf"
        vdf_file.write_text(vdf, encoding="utf-8")
        monkeypatch.setattr(
            "modules.steam_detector._find_loginusers_vdf", lambda: vdf_file
        )
        user = detect_steam_user()
        assert user is not None
        assert user.persona_name == "Alpha"

    def test_returns_none_when_no_vdf_found(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "modules.steam_detector._find_loginusers_vdf", lambda: None
        )
        assert detect_steam_user() is None

    def test_returns_none_when_vdf_file_missing(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        missing = tmp_path / "nonexistent.vdf"
        monkeypatch.setattr(
            "modules.steam_detector._find_loginusers_vdf", lambda: missing
        )
        assert detect_steam_user() is None

    def test_returns_none_for_empty_vdf(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        vdf_file = tmp_path / "loginusers.vdf"
        vdf_file.write_text("", encoding="utf-8")
        monkeypatch.setattr(
            "modules.steam_detector._find_loginusers_vdf", lambda: vdf_file
        )
        assert detect_steam_user() is None


class TestDetectAllSteamUsers:
    """Tests for detect_all_steam_users() using monkeypatch."""

    def test_returns_all_users(self, tmp_path: Path, monkeypatch) -> None:
        vdf_file = tmp_path / "loginusers.vdf"
        vdf_file.write_text(SAMPLE_VDF, encoding="utf-8")
        monkeypatch.setattr(
            "modules.steam_detector._find_loginusers_vdf", lambda: vdf_file
        )
        users = detect_all_steam_users()
        assert len(users) == 2

    def test_returns_empty_when_no_vdf_found(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "modules.steam_detector._find_loginusers_vdf", lambda: None
        )
        assert detect_all_steam_users() == []

    def test_returns_empty_when_vdf_file_missing(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        missing = tmp_path / "nonexistent.vdf"
        monkeypatch.setattr(
            "modules.steam_detector._find_loginusers_vdf", lambda: missing
        )
        assert detect_all_steam_users() == []
