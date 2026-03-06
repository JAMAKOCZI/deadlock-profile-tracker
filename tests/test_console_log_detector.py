"""Tests for :mod:`modules.console_log_detector`."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from modules.console_log_detector import (
    MATCH_CREATED_RE,
    MATCH_DESTROYED_RE,
    _find_deadlock_install,
    find_match_id_in_console_log,
    get_console_log_path,
)


# ── regex patterns ───────────────────────────────────────────────────


class TestMatchCreatedRe:
    def test_standard_line(self) -> None:
        m = MATCH_CREATED_RE.search("Lobby 12345678 for Match 9876543210 created")
        assert m is not None
        assert m.group(2) == "9876543210"

    def test_case_insensitive(self) -> None:
        m = MATCH_CREATED_RE.search("LOBBY 111 for MATCH 222 CREATED")
        assert m is not None
        assert m.group(2) == "222"

    def test_extra_whitespace(self) -> None:
        m = MATCH_CREATED_RE.search("Lobby  99  for  Match  777  created")
        assert m is not None
        assert m.group(2) == "777"

    def test_no_match(self) -> None:
        assert MATCH_CREATED_RE.search("nothing here") is None


class TestMatchDestroyedRe:
    def test_standard_line(self) -> None:
        m = MATCH_DESTROYED_RE.search("Lobby 12345678 for Match 9876543210 destroyed")
        assert m is not None
        assert m.group(2) == "9876543210"

    def test_no_match(self) -> None:
        assert MATCH_DESTROYED_RE.search("nothing here") is None


# ── _find_deadlock_install ───────────────────────────────────────────


class TestFindDeadlockInstall:
    def test_env_override_existing(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr("config.DEADLOCK_PATH", str(tmp_path))
        result = _find_deadlock_install()
        assert result == tmp_path

    def test_env_override_nonexistent(self, tmp_path: Path, monkeypatch) -> None:
        nonexistent = tmp_path / "no_such_dir"
        monkeypatch.setattr("config.DEADLOCK_PATH", str(nonexistent))
        # Should fall through to VDF scan and return None (no Steam on CI)
        result = _find_deadlock_install()
        assert result is None or isinstance(result, Path)

    def test_empty_env_falls_through(self, monkeypatch) -> None:
        monkeypatch.setattr("config.DEADLOCK_PATH", "")
        result = _find_deadlock_install()
        assert result is None or isinstance(result, Path)

    def test_vdf_scan_finds_deadlock(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr("config.DEADLOCK_PATH", "")

        # Build a fake Steam root under tmp_path
        steam_root = tmp_path / "Steam"
        steamapps_dir = steam_root / "steamapps"
        deadlock_dir = steamapps_dir / "common" / "Deadlock"
        deadlock_dir.mkdir(parents=True)

        # Realistic libraryfolders.vdf pointing a library path at steam_root
        vdf_content = (
            '"LibraryFolders"\n'
            "{\n"
            '    "1"\n'
            "    {\n"
            f'        "path"\t"{steam_root}"\n'
            "    }\n"
            "}\n"
        )
        (steamapps_dir / "libraryfolders.vdf").write_text(vdf_content, encoding="utf-8")

        # Redirect the PROGRAMFILES(X86) env var so steam_roots includes our fake Steam root
        monkeypatch.setenv("PROGRAMFILES(X86)", str(tmp_path))

        result = _find_deadlock_install()
        assert result == deadlock_dir


# ── get_console_log_path ─────────────────────────────────────────────


class TestGetConsoleLogPath:
    def test_returns_path_when_exists(self, tmp_path: Path, monkeypatch) -> None:
        log_file = tmp_path / "game" / "citadel" / "console.log"
        log_file.parent.mkdir(parents=True)
        log_file.write_text("some log", encoding="utf-8")

        monkeypatch.setattr(
            "modules.console_log_detector._find_deadlock_install", lambda: tmp_path
        )
        result = get_console_log_path()
        assert result == log_file

    def test_returns_none_when_log_missing(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr(
            "modules.console_log_detector._find_deadlock_install", lambda: tmp_path
        )
        result = get_console_log_path()
        assert result is None

    def test_returns_none_when_install_not_found(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "modules.console_log_detector._find_deadlock_install", lambda: None
        )
        result = get_console_log_path()
        assert result is None


# ── find_match_id_in_console_log ─────────────────────────────────────


class TestFindMatchIdInConsoleLog:
    def _write_log(self, tmp_path: Path, content: str) -> Path:
        log_file = tmp_path / "game" / "citadel" / "console.log"
        log_file.parent.mkdir(parents=True)
        log_file.write_text(content, encoding="utf-8")
        return log_file

    def test_returns_match_id_from_active_match(self, tmp_path: Path, monkeypatch) -> None:
        self._write_log(
            tmp_path,
            "Some log line\nLobby 12345678 for Match 9876543210 created\nMore log\n",
        )
        monkeypatch.setattr(
            "modules.console_log_detector._find_deadlock_install", lambda: tmp_path
        )
        assert find_match_id_in_console_log() == 9876543210

    def test_returns_none_when_match_destroyed(self, tmp_path: Path, monkeypatch) -> None:
        self._write_log(
            tmp_path,
            "Lobby 12345678 for Match 9876543210 created\n"
            "Lobby 12345678 for Match 9876543210 destroyed\n",
        )
        monkeypatch.setattr(
            "modules.console_log_detector._find_deadlock_install", lambda: tmp_path
        )
        assert find_match_id_in_console_log() is None

    def test_returns_latest_match_id(self, tmp_path: Path, monkeypatch) -> None:
        self._write_log(
            tmp_path,
            "Lobby 1 for Match 111 created\n"
            "Lobby 1 for Match 111 destroyed\n"
            "Lobby 2 for Match 222 created\n",
        )
        monkeypatch.setattr(
            "modules.console_log_detector._find_deadlock_install", lambda: tmp_path
        )
        assert find_match_id_in_console_log() == 222

    def test_returns_none_when_no_created_events(self, tmp_path: Path, monkeypatch) -> None:
        self._write_log(tmp_path, "No match events here\n")
        monkeypatch.setattr(
            "modules.console_log_detector._find_deadlock_install", lambda: tmp_path
        )
        assert find_match_id_in_console_log() is None

    def test_returns_none_when_log_not_found(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "modules.console_log_detector._find_deadlock_install", lambda: None
        )
        assert find_match_id_in_console_log() is None

    def test_reads_only_tail_of_large_file(self, tmp_path: Path, monkeypatch) -> None:
        from modules.console_log_detector import TAIL_BYTES

        # Write an old event before the tail window (should be ignored)
        old_event = "Lobby 0 for Match 000 created\n"
        # Use line-based filler so readline() only skips one partial line,
        # not the new_event that follows.
        filler_line = "X" * 100 + "\n"
        num_lines = (TAIL_BYTES // len(filler_line)) + 2
        filler = filler_line * num_lines
        new_event = "Lobby 1 for Match 999 created\n"
        content = old_event + filler + new_event

        self._write_log(tmp_path, content)
        monkeypatch.setattr(
            "modules.console_log_detector._find_deadlock_install", lambda: tmp_path
        )
        result = find_match_id_in_console_log()
        # The new event is within the tail window
        assert result == 999

    def test_destroyed_for_different_match_id_does_not_hide_active(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        self._write_log(
            tmp_path,
            "Lobby 1 for Match 111 created\n"
            "Lobby 2 for Match 222 created\n"
            "Lobby 1 for Match 111 destroyed\n",
        )
        monkeypatch.setattr(
            "modules.console_log_detector._find_deadlock_install", lambda: tmp_path
        )
        # Match 222 is still active; 111 was destroyed but it's not the last created
        assert find_match_id_in_console_log() == 222

    def test_returns_none_on_oserror(self, tmp_path: Path, monkeypatch) -> None:
        log_file = tmp_path / "game" / "citadel" / "console.log"
        log_file.parent.mkdir(parents=True)
        log_file.write_text("", encoding="utf-8")
        monkeypatch.setattr(
            "modules.console_log_detector._find_deadlock_install", lambda: tmp_path
        )
        # Make open raise OSError
        with patch("builtins.open", side_effect=OSError("simulated")):
            assert find_match_id_in_console_log() is None
