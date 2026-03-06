"""Tests for modules/steamid_converter.py."""

import pytest

from modules.steamid_converter import (
    _STEAM_ID64_OFFSET,
    account_id_to_steam_id64,
    steam_id64_to_account_id,
)


class TestAccountIdToSteamId64:
    def test_known_conversion(self):
        # Example: account_id 1 → SteamID64 76561197960265729
        assert account_id_to_steam_id64(1) == _STEAM_ID64_OFFSET + 1

    def test_large_account_id(self):
        account_id = 123456789
        result = account_id_to_steam_id64(account_id)
        assert result == account_id + _STEAM_ID64_OFFSET

    def test_round_trip(self):
        original = 987654321
        steam_id64 = account_id_to_steam_id64(original)
        assert steam_id64_to_account_id(steam_id64) == original

    def test_negative_account_id_raises(self):
        with pytest.raises(ValueError, match="must be positive"):
            account_id_to_steam_id64(-1)

    def test_zero_account_id_raises(self):
        with pytest.raises(ValueError, match="must be positive"):
            account_id_to_steam_id64(0)


class TestSteamId64ToAccountId:
    def test_known_conversion(self):
        steam_id64 = _STEAM_ID64_OFFSET + 42
        assert steam_id64_to_account_id(steam_id64) == 42

    def test_too_small_value_raises(self):
        with pytest.raises(ValueError, match="must be >"):
            steam_id64_to_account_id(100)

    def test_exactly_offset_raises(self):
        with pytest.raises(ValueError, match="must be >"):
            steam_id64_to_account_id(_STEAM_ID64_OFFSET)
