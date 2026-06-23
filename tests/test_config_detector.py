"""Unit tests for tooldex/core/discovery/config_detector.py."""
import json

import pytest

from tooldex.core.discovery.config_detector import _merge, _project_slug, detect_all
from tooldex.core.discovery.results import ConfigDetectionResult, DiscoverySource, SourceStatus
from tooldex.core.models.server import MCPServer


class TestProjectSlug:
    def test_deterministic(self):
        assert _project_slug("/home/user/project") == _project_slug("/home/user/project")

    def test_different_paths_differ(self):
        assert _project_slug("/a") != _project_slug("/b")

    def test_no_slashes_in_output(self):
        assert "/" not in _project_slug("/home/user/project")

    def test_length_is_ten(self):
        assert len(_project_slug("/home/user/project")) == 10


class TestMerge:
    def test_global_server_gets_client_prefixed_id(self):
        result = ConfigDetectionResult()
        server = MCPServer(id="fs", name="fs")
        source = DiscoverySource(client="cursor_user", path="/p", status=SourceStatus.FOUND, servers=[server])
        _merge(result, source, client="cursor_user")
        assert "cursor_user:fs" in result.servers
        assert result.servers["cursor_user:fs"].client == "cursor_user"

    def test_project_scoped_claude_server_remapped(self):
        result = ConfigDetectionResult()
        server = MCPServer(id="db", name="db", project_path="/home/user/proj")
        source = DiscoverySource(client="claude_code_user", path="/p", status=SourceStatus.FOUND, servers=[server])
        _merge(result, source, client="claude_code_user")
        qid = next(iter(result.servers))
        assert qid.startswith("claude_code_project:")
        assert result.servers[qid].client == "claude_code_project"

    def test_first_sighting_wins_on_duplicate_qualified_id(self):
        result = ConfigDetectionResult()
        first = MCPServer(id="fs", name="fs", command="first")
        second = MCPServer(id="fs", name="fs", command="second")
        src1 = DiscoverySource(client="cursor_user", path="/p1", status=SourceStatus.FOUND, servers=[first])
        src2 = DiscoverySource(client="cursor_user", path="/p2", status=SourceStatus.FOUND, servers=[second])
        _merge(result, src1, client="cursor_user")
        _merge(result, src2, client="cursor_user")
        assert result.servers["cursor_user:fs"].command == "first"
        assert len(result.duplicates) == 1

    def test_cross_client_name_collision_recorded(self):
        result = ConfigDetectionResult()
        s1 = MCPServer(id="browserbase", name="browserbase")
        s2 = MCPServer(id="browserbase", name="browserbase")
        src1 = DiscoverySource(client="claude_code_user", path="/p1", status=SourceStatus.FOUND, servers=[s1])
        src2 = DiscoverySource(client="cursor_user", path="/p2", status=SourceStatus.FOUND, servers=[s2])
        _merge(result, src1, client="claude_code_user")
        _merge(result, src2, client="cursor_user")
        assert any("also configured in" in d for d in result.duplicates)
        assert result.server_count == 2

    def test_in_file_duplicates_recorded(self):
        result = ConfigDetectionResult()
        source = DiscoverySource(
            client="cursor_user", path="/p", status=SourceStatus.FOUND,
            servers=[], in_file_duplicates=["fs"],
        )
        _merge(result, source, client="cursor_user")
        assert any("duplicate key" in d for d in result.duplicates)


class TestDetectAll:
    def test_custom_paths_processed_and_win_on_collision(self, tmp_path, monkeypatch):
        custom = tmp_path / "custom.json"
        custom.write_text(json.dumps({"mcpServers": {"fs": {"command": "from-custom"}}}))

        # Skip all built-in autodetection so only the custom path is exercised.
        result = detect_all(
            cwd=tmp_path,
            env={},
            custom_paths=[custom],
            auto_detect=False,
        )
        assert "custom:fs" in result.servers
        assert result.servers["custom:fs"].command == "from-custom"

    def test_auto_detect_false_skips_builtin_sources(self, tmp_path):
        result = detect_all(cwd=tmp_path, env={}, auto_detect=False)
        assert result.sources == []
        assert result.servers == {}

    def test_returns_config_detection_result_instance(self, tmp_path):
        result = detect_all(cwd=tmp_path, env={}, auto_detect=False)
        assert isinstance(result, ConfigDetectionResult)
