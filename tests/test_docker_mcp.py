"""Unit tests for tooldex/core/discovery/_docker_mcp.py.

All tests mock subprocess.run — never shells out to a real `docker` binary.
"""
import json
import subprocess
from unittest.mock import patch

from tooldex.core.discovery import _docker_mcp
from tooldex.core.discovery.results import SourceStatus


def _proc(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


class TestRun:
    def test_returns_stdout_on_success(self):
        with patch("subprocess.run", return_value=_proc(0, stdout="hello")):
            assert _docker_mcp._run("profile", "ls") == "hello"

    def test_none_when_docker_not_installed(self):
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            assert _docker_mcp._run("profile", "ls") is None

    def test_none_on_timeout(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="docker", timeout=10)):
            assert _docker_mcp._run("profile", "ls") is None

    def test_none_on_nonzero_exit(self):
        with patch("subprocess.run", return_value=_proc(1, stderr="unknown command")):
            assert _docker_mcp._run("profile", "ls") is None

    def test_none_on_os_error(self):
        with patch("subprocess.run", side_effect=OSError("permission denied")):
            assert _docker_mcp._run("profile", "ls") is None


class TestParseServerEntry:
    def test_valid_entry_with_tools(self):
        entry = {
            "image": "mcp/fetch",
            "snapshot": {
                "server": {
                    "name": "fetch",
                    "title": "Fetch",
                    "description": "Fetch URLs",
                    "command": ["--port", "8080"],
                    "tools": [
                        {"name": "fetch_url", "description": "Fetch a URL"},
                        {"name": "no_desc"},
                    ],
                }
            },
        }
        server = _docker_mcp._parse_server_entry(entry)
        assert server is not None
        assert server.id == "fetch"
        assert server.name == "Fetch"
        assert server.command == "docker"
        assert server.args == ["run", "-i", "--rm", "mcp/fetch", "--port", "8080"]
        assert len(server.discovered_tools) == 2
        assert server.discovered_tools[0].name == "fetch_url"

    def test_missing_server_name_returns_none(self):
        entry = {"snapshot": {"server": {"title": "No ID"}}}
        assert _docker_mcp._parse_server_entry(entry) is None

    def test_no_image_produces_no_run_args(self):
        entry = {"snapshot": {"server": {"name": "srv"}}}
        server = _docker_mcp._parse_server_entry(entry)
        assert server.args == []
        assert server.command is None

    def test_malformed_tool_entries_are_filtered_out(self):
        entry = {
            "image": "img",
            "snapshot": {"server": {
                "name": "srv",
                "tools": [{"name": "good"}, {"no_name": True}, "not_a_dict", None],
            }},
        }
        server = _docker_mcp._parse_server_entry(entry)
        assert len(server.discovered_tools) == 1
        assert server.discovered_tools[0].name == "good"

    def test_falls_back_to_server_name_when_no_title(self):
        entry = {"snapshot": {"server": {"name": "srv"}}}
        server = _docker_mcp._parse_server_entry(entry)
        assert server.name == "srv"

    def test_empty_dict_returns_none(self):
        assert _docker_mcp._parse_server_entry({}) is None


class TestSourceFromProfileDict:
    def test_profile_with_servers_is_found(self):
        data = {"id": "myprofile", "servers": [
            {"snapshot": {"server": {"name": "a"}}},
        ]}
        source = _docker_mcp._source_from_profile_dict(data)
        assert source.status == SourceStatus.FOUND
        assert source.client == "docker_mcp:myprofile"
        assert len(source.servers) == 1

    def test_profile_with_no_servers_is_empty(self):
        source = _docker_mcp._source_from_profile_dict({"id": "empty", "servers": []})
        assert source.status == SourceStatus.EMPTY
        assert source.servers == []

    def test_malformed_entries_are_skipped_not_fatal(self):
        data = {"id": "p", "servers": [
            {"snapshot": {"server": {"name": "good"}}},
            {"snapshot": {"server": {}}},  # missing name -> skipped
            "not_a_dict",  # skipped
        ]}
        source = _docker_mcp._source_from_profile_dict(data)
        assert len(source.servers) == 1
        assert source.servers[0].id == "good"

    def test_falls_back_to_name_when_no_id(self):
        source = _docker_mcp._source_from_profile_dict({"name": "byname", "servers": []})
        assert source.client == "docker_mcp:byname"

    def test_unknown_when_neither_id_nor_name(self):
        source = _docker_mcp._source_from_profile_dict({"servers": []})
        assert source.client == "docker_mcp:unknown"


class TestProfileIdsFromText:
    def test_parses_ids_skipping_header_and_separators(self):
        text = "ID        NAME\n----      ----\ntooldex   tooldex\nrochh     rochh\n"
        with patch("subprocess.run", return_value=_proc(0, stdout=text)):
            assert _docker_mcp._profile_ids_from_text() == ["tooldex", "rochh"]

    def test_empty_output_returns_empty_list(self):
        with patch("subprocess.run", return_value=_proc(0, stdout="")):
            assert _docker_mcp._profile_ids_from_text() == []

    def test_docker_missing_returns_empty_list(self):
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            assert _docker_mcp._profile_ids_from_text() == []


class TestReadAllDockerMcpProfiles:
    def test_fast_path_used_when_bulk_json_available(self):
        profiles = [{"id": "p1", "servers": [{"snapshot": {"server": {"name": "a"}}}]}]
        with patch("subprocess.run", return_value=_proc(0, stdout=json.dumps(profiles))):
            sources = _docker_mcp.read_all_docker_mcp_profiles()
        assert len(sources) == 1
        assert sources[0].client == "docker_mcp:p1"

    def test_docker_not_installed_returns_empty_list_not_error(self):
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            assert _docker_mcp.read_all_docker_mcp_profiles() == []

    def test_falls_back_to_slow_path_when_bulk_json_empty(self):
        list_text = "ID        NAME\n----      ----\np1        p1\n"
        show_json = json.dumps({"id": "p1", "servers": [{"snapshot": {"server": {"name": "a"}}}]})

        def fake_run(cmd, **kwargs):
            args = cmd[2:]  # strip ["docker", "mcp"]
            if args[:3] == ["profile", "ls", "--format"]:
                return _proc(0, stdout="")  # bulk JSON path returns nothing usable
            if args[:2] == ["profile", "ls"]:
                return _proc(0, stdout=list_text)
            if args[:2] == ["profile", "show"]:
                return _proc(0, stdout=show_json)
            return _proc(1)

        with patch("subprocess.run", side_effect=fake_run):
            sources = _docker_mcp.read_all_docker_mcp_profiles()

        assert len(sources) == 1
        assert sources[0].client == "docker_mcp:p1"

    def test_fast_path_malformed_json_falls_back_to_slow_path(self):
        def fake_run(cmd, **kwargs):
            args = cmd[2:]
            if args[:3] == ["profile", "ls", "--format"]:
                return _proc(0, stdout="not valid json{{{")
            if args[:2] == ["profile", "ls"]:
                return _proc(0, stdout="")  # no profiles found on slow path either
            return _proc(1)

        with patch("subprocess.run", side_effect=fake_run):
            assert _docker_mcp.read_all_docker_mcp_profiles() == []
