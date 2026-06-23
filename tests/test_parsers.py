"""Unit tests for toolpool/core/discovery/_parsers.py."""
from pathlib import Path

import pytest

from toolpool.core.discovery._parsers import (
    parse_claude_json,
    parse_mcp_servers,
    resolve_dict,
    resolve_env_refs,
    resolve_list,
)


# ---------------------------------------------------------------------------
# resolve_env_refs / resolve_dict / resolve_list
# ---------------------------------------------------------------------------

class TestResolveEnvRefs:
    def test_brace_syntax_resolved(self):
        assert resolve_env_refs("${HOME}/bin", {"HOME": "/home/user"}) == "/home/user/bin"

    def test_bare_syntax_resolved(self):
        assert resolve_env_refs("$HOME/bin", {"HOME": "/home/user"}) == "/home/user/bin"

    def test_unresolved_ref_passes_through(self):
        assert resolve_env_refs("${MISSING}", {}) == "${MISSING}"

    def test_no_refs_returned_unchanged(self):
        assert resolve_env_refs("plain string", {}) == "plain string"

    def test_multiple_refs_in_one_string(self):
        env = {"A": "1", "B": "2"}
        assert resolve_env_refs("${A}-$B", env) == "1-2"

    def test_literal_dollar_without_identifier_untouched(self):
        assert resolve_env_refs("$ not a var", {}) == "$ not a var"


class TestResolveDict:
    def test_resolves_string_values(self):
        out = resolve_dict({"PATH": "${HOME}/bin"}, {"HOME": "/home/user"})
        assert out == {"PATH": "/home/user/bin"}

    def test_skips_non_string_values(self):
        out = resolve_dict({"COUNT": 5}, {})
        assert out == {}

    def test_empty_dict(self):
        assert resolve_dict({}, {}) == {}


class TestResolveList:
    def test_resolves_string_items(self):
        out = resolve_list(["${HOME}/bin", "--flag"], {"HOME": "/home/user"})
        assert out == ["/home/user/bin", "--flag"]

    def test_coerces_non_string_items(self):
        out = resolve_list([1, True], {})
        assert out == ["1", "True"]

    def test_empty_list(self):
        assert resolve_list([], {}) == []


# ---------------------------------------------------------------------------
# parse_mcp_servers
# ---------------------------------------------------------------------------

class TestParseMcpServers:
    def test_parses_stdio_server(self):
        raw = {"mcpServers": {"fs": {"command": "npx", "args": ["-y", "@mcp/fs"]}}}
        servers = parse_mcp_servers(raw, "/cfg.json", env={})
        assert len(servers) == 1
        s = servers[0]
        assert s.id == "fs"
        assert s.name == "fs"
        assert s.transport == "stdio"
        assert s.command == "npx"
        assert s.package == "@mcp/fs"

    def test_parses_http_server(self):
        raw = {"mcpServers": {"remote": {"url": "https://example.com/mcp", "type": "http"}}}
        servers = parse_mcp_servers(raw, "/cfg.json", env={})
        assert servers[0].transport == "http"
        assert servers[0].url == "https://example.com/mcp"

    def test_parses_sse_server(self):
        raw = {"mcpServers": {"remote": {"url": "https://example.com/sse", "type": "sse"}}}
        servers = parse_mcp_servers(raw, "/cfg.json", env={})
        assert servers[0].transport == "sse"

    def test_defaults_to_http_for_unknown_type(self):
        raw = {"mcpServers": {"remote": {"url": "https://example.com", "type": "weird"}}}
        servers = parse_mcp_servers(raw, "/cfg.json", env={})
        assert servers[0].transport == "http"

    def test_missing_key_returns_empty(self):
        assert parse_mcp_servers({}, "/cfg.json", env={}) == []

    def test_wrong_type_for_key_returns_empty(self):
        assert parse_mcp_servers({"mcpServers": "not-a-dict"}, "/cfg.json", env={}) == []

    def test_skips_non_dict_entry(self):
        raw = {"mcpServers": {"bad": "not-an-object", "good": {"command": "npx"}}}
        servers = parse_mcp_servers(raw, "/cfg.json", env={})
        assert len(servers) == 1
        assert servers[0].id == "good"

    def test_skips_disabled_server(self):
        raw = {"mcpServers": {"off": {"command": "npx", "disabled": True}}}
        assert parse_mcp_servers(raw, "/cfg.json", env={}) == []

    def test_skips_server_without_command_or_url(self):
        raw = {"mcpServers": {"broken": {"description": "no transport info"}}}
        assert parse_mcp_servers(raw, "/cfg.json", env={}) == []

    def test_one_bad_server_does_not_break_others(self):
        raw = {"mcpServers": {"broken": {}, "good": {"command": "npx"}}}
        servers = parse_mcp_servers(raw, "/cfg.json", env={})
        assert [s.id for s in servers] == ["good"]

    def test_custom_key_for_codex_style_configs(self):
        raw = {"mcp_servers": {"fs": {"command": "npx"}}}
        servers = parse_mcp_servers(raw, "/cfg.toml", env={}, key="mcp_servers")
        assert len(servers) == 1

    def test_env_vars_resolved_in_command_and_args(self):
        raw = {"mcpServers": {"fs": {"command": "$BIN", "args": ["${ARG}"]}}}
        servers = parse_mcp_servers(raw, "/cfg.json", env={"BIN": "node", "ARG": "value"})
        assert servers[0].command == "node"
        assert servers[0].args == ["value"]

    def test_env_vars_resolved_in_env_block(self):
        raw = {"mcpServers": {"fs": {"command": "npx", "env": {"KEY": "${SECRET}"}}}}
        servers = parse_mcp_servers(raw, "/cfg.json", env={"SECRET": "abc123"})
        assert servers[0].env == {"KEY": "abc123"}

    def test_bearer_token_env_var_resolved(self):
        raw = {"mcpServers": {"api": {"url": "https://x", "bearer_token_env_var": "TOKEN"}}}
        servers = parse_mcp_servers(raw, "/cfg.json", env={"TOKEN": "secret-value"})
        assert servers[0].headers["Authorization"] == "Bearer secret-value"

    def test_bearer_token_falls_back_to_literal_value(self):
        raw = {"mcpServers": {"api": {"url": "https://x", "bearer_token_env_var": "literal-token"}}}
        servers = parse_mcp_servers(raw, "/cfg.json", env={})
        assert servers[0].headers["Authorization"] == "Bearer literal-token"

    def test_uvx_package_inferred_from_dash_from_flag(self):
        raw = {"mcpServers": {"x": {"command": "uvx", "args": ["--from", "mypkg", "entry"]}}}
        servers = parse_mcp_servers(raw, "/cfg.json", env={})
        assert servers[0].package == "mypkg"

    def test_uvx_package_inferred_from_first_positional(self):
        raw = {"mcpServers": {"x": {"command": "uvx", "args": ["entrypoint"]}}}
        servers = parse_mcp_servers(raw, "/cfg.json", env={})
        assert servers[0].package == "entrypoint"

    def test_package_none_for_unknown_command(self):
        raw = {"mcpServers": {"x": {"command": "node", "args": ["index.js"]}}}
        servers = parse_mcp_servers(raw, "/cfg.json", env={})
        assert servers[0].package is None

    def test_uses_os_environ_when_env_not_provided(self, monkeypatch):
        monkeypatch.setenv("TOOLPOOL_TEST_VAR", "from-environ")
        raw = {"mcpServers": {"x": {"command": "$TOOLPOOL_TEST_VAR"}}}
        servers = parse_mcp_servers(raw, "/cfg.json")
        assert servers[0].command == "from-environ"


# ---------------------------------------------------------------------------
# parse_claude_json
# ---------------------------------------------------------------------------

class TestParseClaudeJson:
    def test_user_level_servers_always_included(self, tmp_path):
        raw = {"mcpServers": {"fs": {"command": "npx"}}}
        servers = parse_claude_json(raw, "/cfg.json", cwd=tmp_path, env={})
        assert len(servers) == 1
        assert servers[0].project_path is None

    def test_no_projects_key_returns_user_servers_only(self, tmp_path):
        raw = {"mcpServers": {"fs": {"command": "npx"}}}
        servers = parse_claude_json(raw, "/cfg.json", cwd=tmp_path, env={})
        assert len(servers) == 1

    def test_project_on_walk_up_path_included(self, tmp_path):
        project_dir = tmp_path
        nested = project_dir / "sub"
        nested.mkdir()
        raw = {
            "projects": {
                str(project_dir): {"mcpServers": {"db": {"command": "node"}}},
            }
        }
        servers = parse_claude_json(raw, "/cfg.json", cwd=nested, env={})
        assert len(servers) == 1
        assert servers[0].project_path == str(project_dir)

    def test_project_not_on_walk_up_path_excluded(self, tmp_path):
        unrelated = tmp_path / "unrelated"
        unrelated.mkdir()
        cwd = tmp_path / "other"
        cwd.mkdir()
        raw = {
            "projects": {
                str(unrelated): {"mcpServers": {"db": {"command": "node"}}},
            }
        }
        servers = parse_claude_json(raw, "/cfg.json", cwd=cwd, env={})
        assert servers == []

    def test_invalid_project_path_skipped_gracefully(self, tmp_path):
        raw = {"projects": {"\x00bad-path": {"mcpServers": {"db": {"command": "node"}}}}}
        servers = parse_claude_json(raw, "/cfg.json", cwd=tmp_path, env={})
        assert servers == []

    def test_non_dict_project_entry_skipped(self, tmp_path):
        raw = {"projects": {str(tmp_path): "not-a-dict"}}
        servers = parse_claude_json(raw, "/cfg.json", cwd=tmp_path, env={})
        assert servers == []

    def test_projects_not_a_dict_returns_user_servers(self, tmp_path):
        raw = {"mcpServers": {"fs": {"command": "npx"}}, "projects": "nonsense"}
        servers = parse_claude_json(raw, "/cfg.json", cwd=tmp_path, env={})
        assert len(servers) == 1
