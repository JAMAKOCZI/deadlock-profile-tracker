"""Tests for :mod:`modules.steam_cache_detector`."""

from __future__ import annotations

from pathlib import Path

from modules.steam_cache_detector import (
    _extract_match_id_from_file,
    _find_httpcache_dir,
    _is_host_char,
    _parse_match_id,
    scan_steam_cache_for_match_id,
)


# ── _is_host_char ────────────────────────────────────────────────────


class TestIsHostChar:
    def test_alphanumeric_accepted(self) -> None:
        for ch in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789":
            assert _is_host_char(ord(ch)), f"Expected {ch!r} to be a valid host char"

    def test_dot_accepted(self) -> None:
        assert _is_host_char(ord("."))

    def test_slash_rejected(self) -> None:
        assert not _is_host_char(ord("/"))

    def test_space_rejected(self) -> None:
        assert not _is_host_char(ord(" "))

    def test_colon_rejected(self) -> None:
        assert not _is_host_char(ord(":"))


# ── _parse_match_id ──────────────────────────────────────────────────


class TestParseMatchId:
    """Tests for the core URL-parsing logic."""

    def _make_data(self, url: str) -> bytes:
        return url.encode("ascii")

    def test_valid_url_returns_match_id(self) -> None:
        data = self._make_data("http://replay123.valve.net/1422450/98765432/metadata")
        assert _parse_match_id(data) == 98765432

    def test_no_valve_marker_returns_none(self) -> None:
        data = self._make_data("http://example.com/1422450/12345/foo")
        assert _parse_match_id(data) is None

    def test_host_not_starting_with_replay_returns_none(self) -> None:
        data = self._make_data("http://cache123.valve.net/1422450/12345/foo")
        assert _parse_match_id(data) is None

    def test_path_without_deadlock_app_id_returns_none(self) -> None:
        data = self._make_data("http://replay1.valve.net/9999999/12345/foo")
        assert _parse_match_id(data) is None

    def test_end_marker_space(self) -> None:
        data = self._make_data("http://replay1.valve.net/1422450/55555/foo bar")
        assert _parse_match_id(data) == 55555

    def test_end_marker_null(self) -> None:
        data = b"http://replay1.valve.net/1422450/66666/foo\x00rest"
        assert _parse_match_id(data) == 66666

    def test_end_marker_newline(self) -> None:
        data = self._make_data("http://replay1.valve.net/1422450/77777/foo\nbar")
        assert _parse_match_id(data) == 77777

    def test_end_marker_quote(self) -> None:
        data = self._make_data('http://replay1.valve.net/1422450/88888/foo"bar')
        assert _parse_match_id(data) == 88888

    def test_end_marker_carriage_return(self) -> None:
        data = self._make_data("http://replay1.valve.net/1422450/99999/foo\rbar")
        assert _parse_match_id(data) == 99999

    def test_end_marker_single_quote(self) -> None:
        data = self._make_data("http://replay1.valve.net/1422450/11111/foo'bar")
        assert _parse_match_id(data) == 11111

    def test_empty_bytes_returns_none(self) -> None:
        assert _parse_match_id(b"") is None

    def test_non_numeric_match_id_returns_none(self) -> None:
        data = self._make_data("http://replay1.valve.net/1422450/abc/foo")
        assert _parse_match_id(data) is None

    def test_path_too_short_returns_none(self) -> None:
        # Path only has /app_id with no further segment
        data = self._make_data("http://replay1.valve.net/1422450")
        assert _parse_match_id(data) is None

    def test_binary_garbage_before_url(self) -> None:
        prefix = b"\x00\x01\x02\x03"
        url = b"http://replay2.valve.net/1422450/12121212/meta"
        assert _parse_match_id(prefix + url) == 12121212

    def test_non_replay_valve_host_before_valid_url(self) -> None:
        # First .valve.net occurrence belongs to a non-replay host; the second
        # should still be found and parsed correctly.
        data = (
            b"http://cdn.valve.net/some/other/path "
            b"http://replay9.valve.net/1422450/13131313/meta"
        )
        assert _parse_match_id(data) == 13131313

    def test_wrong_app_id_returns_none(self) -> None:
        # Path starts with a different app id — should not be parsed.
        data = self._make_data("http://replay1.valve.net/9999999/12345/foo")
        assert _parse_match_id(data) is None

    def test_app_id_in_match_id_segment_returns_none(self) -> None:
        # 1422450 appears only as the match_id segment, not as parts[1].
        data = self._make_data("http://replay1.valve.net/9999999/1422450/foo")
        assert _parse_match_id(data) is None


# ── _extract_match_id_from_file ──────────────────────────────────────


class TestExtractMatchIdFromFile:
    def test_valid_file_returns_match_id(self, tmp_path: Path) -> None:
        f = tmp_path / "cache_entry"
        f.write_bytes(b"http://replay5.valve.net/1422450/20202020/data")
        assert _extract_match_id_from_file(f) == 20202020

    def test_missing_file_returns_none(self, tmp_path: Path) -> None:
        missing = tmp_path / "nonexistent"
        assert _extract_match_id_from_file(missing) is None

    def test_reads_only_first_200_bytes(self, tmp_path: Path) -> None:
        # The URL is placed beyond byte 200 — should NOT be found.
        padding = b"X" * 200
        url = b"http://replay5.valve.net/1422450/30303030/data"
        f = tmp_path / "large_entry"
        f.write_bytes(padding + url)
        assert _extract_match_id_from_file(f) is None

    def test_url_within_first_200_bytes_found(self, tmp_path: Path) -> None:
        # URL starts at byte 100 (within the 200-byte read window).
        padding = b"X" * 100
        url = b"http://replay6.valve.net/1422450/40404040/d"
        f = tmp_path / "offset_entry"
        f.write_bytes(padding + url)
        assert _extract_match_id_from_file(f) == 40404040


# ── scan_steam_cache_for_match_id ────────────────────────────────────


class TestScanSteamCacheForMatchId:
    def test_finds_match_id_in_cache_dir(self, tmp_path: Path, monkeypatch) -> None:
        subdir = tmp_path / "sub"
        subdir.mkdir()
        (subdir / "file1").write_bytes(b"junk data without any marker")
        (subdir / "file2").write_bytes(
            b"http://replay7.valve.net/1422450/50505050/meta"
        )
        monkeypatch.setattr(
            "modules.steam_cache_detector._find_httpcache_dir", lambda: tmp_path
        )
        result = scan_steam_cache_for_match_id()
        assert result == 50505050

    def test_returns_none_when_no_match_in_cache(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        (tmp_path / "file1").write_bytes(b"no valve url here")
        monkeypatch.setattr(
            "modules.steam_cache_detector._find_httpcache_dir", lambda: tmp_path
        )
        assert scan_steam_cache_for_match_id() is None

    def test_returns_none_when_cache_dir_not_found(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "modules.steam_cache_detector._find_httpcache_dir", lambda: None
        )
        assert scan_steam_cache_for_match_id() is None

    def test_returns_none_when_cache_dir_missing(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        missing_dir = tmp_path / "nonexistent"
        monkeypatch.setattr(
            "modules.steam_cache_detector._find_httpcache_dir", lambda: missing_dir
        )
        assert scan_steam_cache_for_match_id() is None

    def test_skips_unreadable_files_gracefully(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        good = tmp_path / "good"
        good.write_bytes(b"http://replay8.valve.net/1422450/60606060/x")
        # Create a subdirectory named the same as a file to cause an OSError on read
        bad_dir = tmp_path / "bad_dir"
        bad_dir.mkdir()
        monkeypatch.setattr(
            "modules.steam_cache_detector._find_httpcache_dir", lambda: tmp_path
        )
        result = scan_steam_cache_for_match_id()
        assert result == 60606060

    def test_returns_none_on_oserror(self, monkeypatch) -> None:
        def _raise():
            raise OSError("simulated OS error")

        monkeypatch.setattr(
            "modules.steam_cache_detector._find_httpcache_dir", _raise
        )
        assert scan_steam_cache_for_match_id() is None


# ── _find_httpcache_dir (smoke test) ────────────────────────────────


class TestFindHttpcacheDir:
    def test_returns_path_or_none(self) -> None:
        # Just ensure it doesn't raise on the current platform.
        result = _find_httpcache_dir()
        assert result is None or isinstance(result, Path)
