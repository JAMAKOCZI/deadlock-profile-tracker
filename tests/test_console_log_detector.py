"""Tests for :mod:`modules.console_log_detector`."""

from __future__ import annotations

from pathlib import Path

import pytest

from modules.console_log_detector import (
    _find_steam_libraries,
    _parse_active_match_id,
    _tail_read,
    find_match_id_in_console_log,
    get_console_log_path,
)


# ── _parse_active_match_id ───────────────────────────────────────────


class TestParseActiveMatchId:
    """Tests for the core log-parsing logic."""

    def test_returns_match_id_when_created(self) -> None:
        text = "Lobby 12345678 for Match 9876543210 created\n"
        assert _parse_active_match_id(text) == 9876543210

    def test_returns_none_when_no_entry(self) -> None:
        assert _parse_active_match_id("nothing here") is None

    def test_returns_none_when_match_destroyed_after_created(self) -> None:
        text = (
            "Lobby 11111111 for Match 9876543210 created\n"
            "Lobby 11111111 for Match 9876543210 destroyed\n"
        )
        assert _parse_active_match_id(text) is None

    def test_returns_match_id_when_destroyed_refers_to_different_match(self) -> None:
        text = (
            "Lobby 11111111 for Match 1111111111 created\n"
            "Lobby 11111111 for Match 1111111111 destroyed\n"
            "Lobby 22222222 for Match 9876543210 created\n"
        )
        assert _parse_active_match_id(text) == 9876543210

    def test_returns_last_created_match_id(self) -> None:
        text = (
            "Lobby 11111111 for Match 1111111111 created\n"
            "Lobby 11111111 for Match 1111111111 destroyed\n"
            "Lobby 22222222 for Match 2222222222 created\n"
            "Lobby 22222222 for Match 2222222222 destroyed\n"
            "Lobby 33333333 for Match 3333333333 created\n"
        )
        assert _parse_active_match_id(text) == 3333333333

    def test_case_insensitive_matching(self) -> None:
        text = "lobby 12345678 for match 9876543210 CREATED\n"
        assert _parse_active_match_id(text) == 9876543210

    def test_extra_whitespace_between_tokens(self) -> None:
        text = "Lobby  12345678  for  Match  9876543210  created\n"
        assert _parse_active_match_id(text) == 9876543210

    def test_empty_string_returns_none(self) -> None:
        assert _parse_active_match_id("") is None

    def test_only_destroyed_entry_returns_none(self) -> None:
        text = "Lobby 11111111 for Match 9876543210 destroyed\n"
        assert _parse_active_match_id(text) is None

    def test_surrounding_log_noise_ignored(self) -> None:
        text = (
            "[2024.01.01] Some unrelated log line\n"
            "[2024.01.01] Another line\n"
            "Lobby 99999999 for Match 5555555555 created\n"
            "[2024.01.01] Post-match log line\n"
        )
        assert _parse_active_match_id(text) == 5555555555


# ── _tail_read ───────────────────────────────────────────────────────


class TestTailRead:
    def test_reads_entire_small_file(self, tmp_path: Path) -> None:
        f = tmp_path / "console.log"
        f.write_text("hello world\n", encoding="utf-8")
        assert _tail_read(f) == "hello world\n"

    def test_reads_last_50kb_of_large_file(self, tmp_path: Path) -> None:
        f = tmp_path / "console.log"
        # Write 60 KB total; only the last 50 KB should be returned.
        prefix = b"X" * (60 * 1024)
        suffix = b"last part"
        f.write_bytes(prefix + suffix)
        content = _tail_read(f)
        assert content.endswith("last part")
        # The first part should be truncated
        assert len(content.encode("utf-8")) <= 50 * 1024 + len(b"last part")

    def test_raises_oserror_on_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(OSError):
            _tail_read(tmp_path / "nonexistent.log")


# ── find_match_id_in_console_log ─────────────────────────────────────


class TestFindMatchIdInConsoleLog:
    def test_returns_match_id_from_log_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        log = tmp_path / "console.log"
        log.write_text(
            "Lobby 12345678 for Match 9876543210 created\n", encoding="utf-8"
        )
        monkeypatch.setattr(
            "modules.console_log_detector.get_console_log_path", lambda: log
        )
        assert find_match_id_in_console_log() == 9876543210

    def test_returns_none_when_no_log_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "modules.console_log_detector.get_console_log_path", lambda: None
        )
        assert find_match_id_in_console_log() is None

    def test_returns_none_when_match_destroyed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        log = tmp_path / "console.log"
        log.write_text(
            "Lobby 12345678 for Match 9876543210 created\n"
            "Lobby 12345678 for Match 9876543210 destroyed\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(
            "modules.console_log_detector.get_console_log_path", lambda: log
        )
        assert find_match_id_in_console_log() is None

    def test_returns_none_on_oserror(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        missing = tmp_path / "nonexistent.log"
        monkeypatch.setattr(
            "modules.console_log_detector.get_console_log_path", lambda: missing
        )
        assert find_match_id_in_console_log() is None


# ── get_console_log_path ─────────────────────────────────────────────


class TestGetConsoleLogPath:
    def test_returns_path_when_env_override_set_and_file_exists(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Create the expected console.log structure under tmp_path
        log_dir = tmp_path / "game" / "citadel"
        log_dir.mkdir(parents=True)
        log_file = log_dir / "console.log"
        log_file.write_text("", encoding="utf-8")

        monkeypatch.setattr("modules.console_log_detector.DEADLOCK_PATH", str(tmp_path))
        result = get_console_log_path()
        assert result == log_file

    def test_returns_none_when_env_override_set_but_file_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "modules.console_log_detector.DEADLOCK_PATH", str(tmp_path)
        )
        monkeypatch.setattr(
            "modules.console_log_detector._find_steam_libraries", lambda: []
        )
        assert get_console_log_path() is None

    def test_returns_path_found_via_steam_library(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Build the Deadlock directory structure inside a fake Steam library
        deadlock_dir = (
            tmp_path / "steamapps" / "common" / "Deadlock" / "game" / "citadel"
        )
        deadlock_dir.mkdir(parents=True)
        log_file = deadlock_dir / "console.log"
        log_file.write_text("", encoding="utf-8")

        monkeypatch.setattr("modules.console_log_detector.DEADLOCK_PATH", "")
        monkeypatch.setattr(
            "modules.console_log_detector._find_steam_libraries", lambda: [tmp_path]
        )
        result = get_console_log_path()
        assert result == log_file

    def test_returns_none_when_no_libraries_and_no_override(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("modules.console_log_detector.DEADLOCK_PATH", "")
        monkeypatch.setattr(
            "modules.console_log_detector._find_steam_libraries", lambda: []
        )
        assert get_console_log_path() is None


# ── _find_steam_libraries ────────────────────────────────────────────


class TestFindSteamLibraries:
    def test_returns_list(self) -> None:
        # Just ensure the function runs without error on the current platform.
        result = _find_steam_libraries()
        assert isinstance(result, list)

    def test_parses_vdf_paths(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # Simulate a Steam root with a libraryfolders.vdf pointing to an
        # extra library at /extra/steam/lib.
        steam_root = tmp_path / "Steam"
        steamapps = steam_root / "steamapps"
        steamapps.mkdir(parents=True)
        vdf_content = (
            '"LibraryFolders"\n'
            '{\n'
            '    "1"\n'
            '    {\n'
            '        "path"\t\t"/extra/steam/lib"\n'
            '    }\n'
            '}\n'
        )
        (steamapps / "libraryfolders.vdf").write_text(vdf_content, encoding="utf-8")

        # Patch the candidate list to only include our fake steam_root.
        import modules.console_log_detector as mod

        original_candidates_builder = mod._find_steam_libraries

        def patched() -> list[Path]:
            libraries: list[Path] = []
            vdf_path = steam_root / "steamapps" / "libraryfolders.vdf"
            if vdf_path.exists():
                import re
                content = vdf_path.read_text(encoding="utf-8", errors="replace")
                for m in re.finditer(r'"path"\s+"([^"]+)"', content):
                    libraries.append(Path(m.group(1)))
                libraries.append(steam_root)
            return libraries

        monkeypatch.setattr(mod, "_find_steam_libraries", patched)
        result = mod._find_steam_libraries()
        assert Path("/extra/steam/lib") in result
        assert steam_root in result
