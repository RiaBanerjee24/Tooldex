"""Unit tests for _status_claude.py, _status_codex.py, _status_cursor.py.

All tests mock subprocess.run — never shell out to a real claude/codex/cursor-agent CLI.
"""
import subprocess
from unittest.mock import patch

from tooldex.core.discovery import _status_claude, _status_codex, _status_cursor


def _proc(stdout="", returncode=0):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


# ---------------------------------------------------------------------------
# Claude
# ---------------------------------------------------------------------------

class TestFetchClaudeStatus:
    def test_parses_connected_and_failed(self):
        output = (
            "filesystem: npx @modelcontextprotocol/server-filesystem - ✔ Connected\n"
            "github: npx @modelcontextprotocol/server-github - ✘ Failed to connect\n"
        )
        with patch("subprocess.run", return_value=_proc(output)):
            statuses = _status_claude.fetch_claude_status()
        assert statuses == {"filesystem": "connected", "github": "failed"}

    def test_skips_lines_without_separator(self):
        output = "some header line with no dash separator\nfilesystem: cmd - ✔ Connected\n"
        with patch("subprocess.run", return_value=_proc(output)):
            statuses = _status_claude.fetch_claude_status()
        assert statuses == {"filesystem": "connected"}

    def test_claude_not_installed_returns_empty_dict(self):
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            assert _status_claude.fetch_claude_status() == {}

    def test_timeout_returns_empty_dict(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=15)):
            assert _status_claude.fetch_claude_status() == {}

    def test_dedups_cwd_and_project_dirs_by_resolved_path(self, tmp_path):
        with patch("subprocess.run", return_value=_proc("")) as mock_run:
            _status_claude.fetch_claude_status(cwd=tmp_path, project_dirs={tmp_path})
        assert mock_run.call_count == 1  # same resolved path -> queried once

    def test_nonexistent_project_dir_is_skipped_not_fatal(self, tmp_path):
        missing = tmp_path / "does-not-exist"
        with patch("subprocess.run", return_value=_proc("")) as mock_run:
            _status_claude.fetch_claude_status(cwd=tmp_path, project_dirs={missing})
        assert mock_run.call_count == 1  # only cwd, missing dir excluded

    def test_queries_each_distinct_directory(self, tmp_path):
        other = tmp_path / "other"
        other.mkdir()
        with patch("subprocess.run", return_value=_proc("")) as mock_run:
            _status_claude.fetch_claude_status(cwd=tmp_path, project_dirs={other})
        assert mock_run.call_count == 2


# ---------------------------------------------------------------------------
# Codex
# ---------------------------------------------------------------------------

class TestFetchCodexStatus:
    def test_parses_enabled_and_other_as_connected_and_failed(self):
        output = (
            "Name        Command  Status   Auth\n"
            "MCP_DOCKER  docker   enabled  Unsupported\n"
            "broken      foo      error    Unsupported\n"
        )
        with patch("subprocess.run", return_value=_proc(output)):
            statuses = _status_codex.fetch_codex_status()
        assert statuses == {"MCP_DOCKER": "connected", "broken": "failed"}

    def test_multiple_sections_separated_by_blank_line(self):
        output = (
            "Name    Command  Status   Auth\n"
            "srv1    cmd      enabled  x\n"
            "\n"
            "Name    Url  Status   Auth\n"
            "srv2    url  enabled  x\n"
        )
        with patch("subprocess.run", return_value=_proc(output)):
            statuses = _status_codex.fetch_codex_status()
        assert statuses == {"srv1": "connected", "srv2": "connected"}

    def test_lines_before_any_header_are_ignored(self):
        output = "some preamble\nsrv    enabled\n"  # no "Name"/"Status" header seen yet
        with patch("subprocess.run", return_value=_proc(output)):
            assert _status_codex.fetch_codex_status() == {}

    def test_codex_not_installed_returns_empty_dict(self):
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            assert _status_codex.fetch_codex_status() == {}


# ---------------------------------------------------------------------------
# Cursor
# ---------------------------------------------------------------------------

class TestFetchCursorStatus:
    def test_enabled_when_tools_listing_present(self):
        list_output = "filesystem: npx server-filesystem\n"

        def fake_run(cmd, **kwargs):
            if cmd[2] == "list":
                return _proc(list_output)
            if cmd[2] == "list-tools":
                return _proc("Tools for filesystem (5):\n- read_file\n")
            return _proc("")

        with patch("subprocess.run", side_effect=fake_run):
            statuses = _status_cursor.fetch_cursor_status()

        assert statuses == {"filesystem": ("enabled", "5 tools")}

    def test_disabled_when_no_tools_listing(self):
        list_output = "broken: some-cmd\n"

        def fake_run(cmd, **kwargs):
            if cmd[2] == "list":
                return _proc(list_output)
            if cmd[2] == "list-tools":
                return _proc("Error: could not connect")
            return _proc("")

        with patch("subprocess.run", side_effect=fake_run):
            statuses = _status_cursor.fetch_cursor_status()

        assert statuses == {"broken": ("disabled", "Error: could not connect")}

    def test_no_names_returns_empty_dict_without_probing(self):
        with patch("subprocess.run", return_value=_proc("")) as mock_run:
            statuses = _status_cursor.fetch_cursor_status()
        assert statuses == {}
        assert mock_run.call_count == 1  # only the initial "list" call, no list-tools probes

    def test_cursor_agent_not_installed_returns_empty_dict(self):
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            assert _status_cursor.fetch_cursor_status() == {}

    def test_probe_one_handles_missing_binary_gracefully(self):
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            name, entry = _status_cursor._probe_one("srv")
        assert name == "srv"
        assert entry == ("discovered", "discovered")

    def test_probe_one_no_output_falls_back_to_no_output_label(self):
        with patch("subprocess.run", return_value=_proc("")):
            name, entry = _status_cursor._probe_one("srv")
        assert entry == ("disabled", "no output")
