"""Unit tests for tooldex/api/routers/files.py."""
from fastapi.testclient import TestClient

from tooldex.api.app import create_app
from tooldex.core.discovery.results import DiscoverySource, SourceStatus
from tooldex.core.models.server import MCPServer
from tooldex.core.parsers.parser import store_discovery_sources


def client():
    return TestClient(create_app())


class TestListFilesEndpoint:
    def test_empty_sources(self):
        store_discovery_sources([])
        resp = client().get("/api/files")
        assert resp.status_code == 200
        body = resp.json()
        assert body == {"files": [], "total": 0, "found": 0, "not_found": 0, "errors": 0}

    def test_counts_by_status(self):
        store_discovery_sources([
            DiscoverySource(client="claude_code_user", path="~/.claude.json", status=SourceStatus.FOUND,
                             servers=[MCPServer(id="a:fs", name="fs")]),
            DiscoverySource(client="cursor_user", path="~/.cursor/mcp.json", status=SourceStatus.NOT_FOUND),
            DiscoverySource(client="codex", path="~/.codex/config.toml", status=SourceStatus.PARSE_ERROR, error="bad toml"),
        ])
        resp = client().get("/api/files")
        body = resp.json()
        assert body["total"] == 3
        assert body["found"] == 1
        assert body["not_found"] == 1
        assert body["errors"] == 1

    def test_file_entry_shape(self):
        store_discovery_sources([
            DiscoverySource(
                client="claude_code_user", path="~/.claude.json", status=SourceStatus.FOUND,
                servers=[MCPServer(id="a:fs", name="fs"), MCPServer(id="a:gh", name="gh")],
                in_file_duplicates=["fs"],
            ),
        ])
        resp = client().get("/api/files")
        entry = resp.json()["files"][0]
        assert entry["client"] == "claude_code_user"
        assert entry["path"] == "~/.claude.json"
        assert entry["status"] == "found"
        assert entry["server_count"] == 2
        assert set(entry["server_ids"]) == {"a:fs", "a:gh"}
        assert entry["in_file_duplicates"] == ["fs"]
        assert entry["error"] is None

    def test_read_error_also_counted_as_error(self):
        store_discovery_sources([
            DiscoverySource(client="x", path="p", status=SourceStatus.READ_ERROR, error="permission denied"),
        ])
        body = client().get("/api/files").json()
        assert body["errors"] == 1

    def test_empty_status_not_counted_as_found_or_error(self):
        store_discovery_sources([
            DiscoverySource(client="x", path="p", status=SourceStatus.EMPTY),
        ])
        body = client().get("/api/files").json()
        assert body["found"] == 0
        assert body["not_found"] == 0
        assert body["errors"] == 0
        assert body["total"] == 1
