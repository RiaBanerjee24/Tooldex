"""Unit tests for tooldex/core/discovery/_readers.py."""
import json
from pathlib import Path

import pytest

from tooldex.core.discovery._readers import read_codex_toml, read_json
from tooldex.core.discovery.results import SourceStatus


class TestReadJson:
    def test_none_path_returns_none(self):
        assert read_json("client", None) is None

    def test_missing_file_returns_not_found(self, tmp_path):
        path = tmp_path / "missing.json"
        source = read_json("client", path)
        assert source.status == SourceStatus.NOT_FOUND

    def test_valid_config_returns_found(self, tmp_path):
        path = tmp_path / "mcp.json"
        path.write_text(json.dumps({"mcpServers": {"fs": {"command": "npx"}}}))
        source = read_json("client", path, env={})
        assert source.status == SourceStatus.FOUND
        assert len(source.servers) == 1
        assert source.servers[0].id == "fs"

    def test_invalid_json_returns_parse_error(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("{not valid json")
        source = read_json("client", path)
        assert source.status == SourceStatus.PARSE_ERROR
        assert "Invalid JSON" in source.error

    def test_top_level_not_object_returns_parse_error(self, tmp_path):
        path = tmp_path / "list.json"
        path.write_text(json.dumps([1, 2, 3]))
        source = read_json("client", path)
        assert source.status == SourceStatus.PARSE_ERROR

    def test_missing_mcp_servers_key_returns_empty(self, tmp_path):
        path = tmp_path / "other.json"
        path.write_text(json.dumps({"foo": "bar"}))
        source = read_json("client", path)
        assert source.status == SourceStatus.EMPTY

    def test_mcp_servers_wrong_type_returns_parse_error(self, tmp_path):
        path = tmp_path / "bad_shape.json"
        path.write_text(json.dumps({"mcpServers": "nope"}))
        source = read_json("client", path)
        assert source.status == SourceStatus.PARSE_ERROR

    def test_empty_mcp_servers_dict_returns_empty_status(self, tmp_path):
        path = tmp_path / "empty.json"
        path.write_text(json.dumps({"mcpServers": {}}))
        source = read_json("client", path)
        assert source.status == SourceStatus.EMPTY

    def test_duplicate_keys_recorded(self, tmp_path):
        path = tmp_path / "dup.json"
        path.write_text('{"mcpServers": {"fs": {"command": "a"}, "fs": {"command": "b"}}}')
        source = read_json("client", path, env={})
        assert source.in_file_duplicates == ["fs"]
        # Last value wins per JSON semantics.
        assert source.servers[0].command == "b"

    def test_client_and_path_set_correctly(self, tmp_path):
        path = tmp_path / "mcp.json"
        path.write_text(json.dumps({"mcpServers": {"fs": {"command": "npx"}}}))
        source = read_json("my_client", path)
        assert source.client == "my_client"
        assert source.path == str(path)


class TestReadCodexToml:
    def test_missing_file_returns_not_found(self, tmp_path):
        path = tmp_path / "config.toml"
        source = read_codex_toml(path, client="codex")
        assert source.status == SourceStatus.NOT_FOUND

    def test_valid_toml_returns_found(self, tmp_path):
        path = tmp_path / "config.toml"
        path.write_text(
            '[mcp_servers.fs]\ncommand = "npx"\nargs = ["-y", "@mcp/fs"]\n'
        )
        source = read_codex_toml(path, client="codex", env={})
        assert source.status == SourceStatus.FOUND
        assert source.servers[0].id == "fs"
        assert source.servers[0].command == "npx"

    def test_invalid_toml_returns_parse_error(self, tmp_path):
        path = tmp_path / "config.toml"
        path.write_text("not = [valid toml")
        source = read_codex_toml(path, client="codex")
        assert source.status == SourceStatus.PARSE_ERROR

    def test_http_server_with_bearer_token(self, tmp_path):
        path = tmp_path / "config.toml"
        path.write_text(
            '[mcp_servers.github]\ntype = "http"\nurl = "https://api.githubcopilot.com/mcp/"\n'
        )
        source = read_codex_toml(path, client="codex", env={})
        assert source.servers[0].transport == "http"
        assert source.servers[0].url == "https://api.githubcopilot.com/mcp/"
