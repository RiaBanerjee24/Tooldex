"""Unit tests for tooldex/api/routers/servers.py."""
import pytest
from fastapi.testclient import TestClient

from tooldex.api.app import create_app
from tooldex.api.routers.servers import _friendly_path, _is_sensitive_env, _redact_server
from tooldex.core.models.manifest import TooldexManifest, TooldexMetadata
from tooldex.core.models.server import DiscoveredToolLite, MCPServer
from tooldex.core.parsers.parser import init_parser_from_manifest


@pytest.fixture
def client():
    return TestClient(create_app())


def _install_manifest(servers: dict[str, MCPServer]):
    manifest = TooldexManifest(metadata=TooldexMetadata(name="Test"), servers=servers)
    init_parser_from_manifest(manifest)
    return manifest


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

class TestIsSensitiveEnv:
    @pytest.mark.parametrize("name", ["API_KEY", "SECRET", "AUTH_TOKEN", "DB_PASSWORD", "apikey"])
    def test_sensitive_names(self, name):
        assert _is_sensitive_env(name) is True

    @pytest.mark.parametrize("name", ["HOST", "PORT", "DEBUG", "PATH"])
    def test_non_sensitive_names(self, name):
        assert _is_sensitive_env(name) is False


class TestFriendlyPath:
    def test_none_returns_none(self):
        assert _friendly_path(None) is None

    def test_empty_string_returns_none(self):
        assert _friendly_path("") is None

    def test_path_under_home_gets_tilde_prefix(self, monkeypatch, tmp_path):
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        target = tmp_path / ".cursor" / "mcp.json"
        assert _friendly_path(str(target)) == "~.cursor/mcp.json"

    def test_path_outside_home_returned_unchanged(self, monkeypatch, tmp_path):
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "home")
        assert _friendly_path("/etc/elsewhere/mcp.json") == "/etc/elsewhere/mcp.json"


class TestRedactServer:
    def test_redacts_sensitive_headers(self):
        out = _redact_server({"headers": {"Authorization": "Bearer abc", "X-Custom": "keep-me"}})
        assert out["headers"]["Authorization"] == "***"
        assert out["headers"]["X-Custom"] == "keep-me"

    def test_redacts_sensitive_env_vars(self):
        out = _redact_server({"env": {"API_KEY": "abc123", "HOST": "localhost"}})
        assert out["env"]["API_KEY"] == "***"
        assert out["env"]["HOST"] == "localhost"

    def test_no_headers_or_env_passthrough(self):
        out = _redact_server({"name": "fs"})
        assert out == {"name": "fs"}

    def test_does_not_mutate_input(self):
        original = {"headers": {"Authorization": "secret"}}
        _redact_server(original)
        assert original["headers"]["Authorization"] == "secret"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

class TestListServersEndpoint:
    def test_empty_manifest(self, client):
        _install_manifest({})
        resp = client.get("/api/servers")
        assert resp.status_code == 200
        body = resp.json()
        assert body["servers"] == []
        assert body["total"] == 0
        assert body["total_tools"] == 0

    def test_redacts_secrets_in_response(self, client):
        server = MCPServer(id="a:fs", name="fs", env={"API_KEY": "super-secret"})
        _install_manifest({"a:fs": server})
        resp = client.get("/api/servers")
        body = resp.json()
        assert body["servers"][0]["env"]["API_KEY"] == "***"

    def test_tool_count_reflects_discovered_tools(self, client):
        server = MCPServer(
            id="a:fs", name="fs",
            discovered_tools=[DiscoveredToolLite(name="read_file")],
        )
        _install_manifest({"a:fs": server})
        resp = client.get("/api/servers")
        body = resp.json()
        assert body["servers"][0]["tool_count"] == 1
        assert body["total_tools"] == 1


class TestGetServerEndpoint:
    def test_found(self, client):
        server = MCPServer(id="a:fs", name="fs")
        _install_manifest({"a:fs": server})
        resp = client.get("/api/servers/a:fs")
        assert resp.status_code == 200
        assert resp.json()["name"] == "fs"

    def test_not_found_returns_404(self, client):
        _install_manifest({})
        resp = client.get("/api/servers/missing")
        assert resp.status_code == 404


class TestHealthEndpoint:
    def test_returns_ok(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
