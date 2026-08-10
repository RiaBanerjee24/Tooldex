"""Unit tests for tooldex/api/routers/servers.py."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from tooldex.api.app import create_app
from tooldex.api.redact import friendly_path, _is_sensitive_env, redact_server
from tooldex.api.routers.servers import rescan_server
from tooldex.core.discovery.results import DiscoveredTool, ToolDiscoveryResult, ToolDiscoveryStatus
from tooldex.core.models.manifest import TooldexManifest, TooldexMetadata
from tooldex.core.models.server import DiscoveredToolLite, MCPServer
from tooldex.core.parsers.parser import get_parser, init_parser_from_manifest


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
        assert friendly_path(None) is None

    def test_empty_string_returns_none(self):
        assert friendly_path("") is None

    def test_path_under_home_gets_tilde_prefix(self, monkeypatch, tmp_path):
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        target = tmp_path / ".cursor" / "mcp.json"
        assert friendly_path(str(target)) == "~.cursor/mcp.json"

    def test_path_outside_home_returned_unchanged(self, monkeypatch, tmp_path):
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "home")
        assert friendly_path("/etc/elsewhere/mcp.json") == "/etc/elsewhere/mcp.json"


class TestRedactServer:
    def test_redacts_sensitive_headers(self):
        out = redact_server({"headers": {"Authorization": "Bearer abc", "X-Custom": "keep-me"}})
        assert out["headers"]["Authorization"] == "***"
        assert out["headers"]["X-Custom"] == "keep-me"

    def test_redacts_sensitive_env_vars(self):
        out = redact_server({"env": {"API_KEY": "abc123", "HOST": "localhost"}})
        assert out["env"]["API_KEY"] == "***"
        assert out["env"]["HOST"] == "localhost"

    def test_no_headers_or_env_passthrough(self):
        out = redact_server({"name": "fs"})
        assert out == {"name": "fs"}

    def test_does_not_mutate_input(self):
        original = {"headers": {"Authorization": "secret"}}
        redact_server(original)
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

    def test_server_id_containing_slash_is_routable(self, client):
        # VSCode/Copilot MCP gallery servers use "publisher/repo"-style names
        # (e.g. "coplaydev/unity-mcp"), so qualified ids contain a literal "/".
        # Regression test: this requires the {server_id:path} converter —
        # the default FastAPI str converter can't match across a "/".
        server = MCPServer(id="vscode_project:coplaydev/unity-mcp", name="coplaydev/unity-mcp")
        _install_manifest({"vscode_project:coplaydev/unity-mcp": server})
        resp = client.get("/api/servers/vscode_project:coplaydev/unity-mcp")
        assert resp.status_code == 200
        assert resp.json()["name"] == "coplaydev/unity-mcp"

    def test_server_id_containing_slash_percent_encoded_is_routable(self, client):
        server = MCPServer(id="vscode_project:coplaydev/unity-mcp", name="coplaydev/unity-mcp")
        _install_manifest({"vscode_project:coplaydev/unity-mcp": server})
        resp = client.get("/api/servers/vscode_project%3Acoplaydev%2Funity-mcp")
        assert resp.status_code == 200
        assert resp.json()["name"] == "coplaydev/unity-mcp"

    def test_sub_route_not_shadowed_by_slash_containing_id(self, client):
        # get_server uses a greedy {server_id:path} catch-all and is registered
        # last specifically so it doesn't swallow /llm-scan/status as part of
        # the id — verify that still holds for a slash-containing id.
        server = MCPServer(id="vscode_project:coplaydev/unity-mcp", name="coplaydev/unity-mcp")
        _install_manifest({"vscode_project:coplaydev/unity-mcp": server})
        resp = client.get("/api/servers/vscode_project:coplaydev/unity-mcp/llm-scan/status")
        assert resp.status_code == 200
        assert resp.json()["status"] == "idle"


def _finding(severity="HIGH", analyzer="YARA", tool_name="t1"):
    return SimpleNamespace(severity=severity, analyzer=analyzer, threat_category="secrets", summary="found a thing")


def _tool_scan_result(tool_name="t1", findings=None):
    findings = findings or []
    return SimpleNamespace(tool_name=tool_name, is_safe=not findings, findings=findings)


class TestRescanServerEndpoint:
    @pytest.mark.asyncio
    async def test_not_found_returns_404(self):
        _install_manifest({})
        with pytest.raises(HTTPException) as exc_info:
            await rescan_server("missing")
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_reruns_yara_scan_by_default(self):
        server = MCPServer(id="a:fs", name="fs", transport="stdio", command="npx")
        _install_manifest({"a:fs": server})
        probe_result = ToolDiscoveryResult(
            server_id="a:fs", status=ToolDiscoveryStatus.FOUND,
            tools=[DiscoveredTool(name="t1", server_id="a:fs", description="d")],
            duration_ms=10,
        )
        scan_results = {"a:fs": [_tool_scan_result("t1", [_finding()])]}
        with patch("tooldex.core.discovery.tool_discovery.list_tools_for", return_value=probe_result), \
             patch("tooldex.core.discovery.probe_cache.invalidate"), \
             patch("tooldex.scanner.scan_servers", return_value=scan_results) as mock_scan:
            result = await rescan_server("a:fs")

        mock_scan.assert_called_once()
        assert result["security_scanned"] is True
        updated = get_parser().manifest.get_server("a:fs")
        assert updated.security_risk == "HIGH"
        assert updated.security_scanned is True
        assert len(updated.security_findings) == 1

    @pytest.mark.asyncio
    async def test_yara_rescan_preserves_existing_llm_findings(self):
        llm_finding = {"tool_name": "t1", "severity": "MEDIUM", "analyzer": "LLM", "summary": "llm found something"}
        server = MCPServer(
            id="a:fs", name="fs", transport="stdio", command="npx",
            security_findings=[llm_finding], security_risk="MEDIUM", security_scanned=True,
        )
        _install_manifest({"a:fs": server})
        probe_result = ToolDiscoveryResult(
            server_id="a:fs", status=ToolDiscoveryStatus.FOUND,
            tools=[DiscoveredTool(name="t1", server_id="a:fs", description="d")],
        )
        # Fresh YARA pass comes back clean — the pre-existing LLM finding must survive.
        with patch("tooldex.core.discovery.tool_discovery.list_tools_for", return_value=probe_result), \
             patch("tooldex.core.discovery.probe_cache.invalidate"), \
             patch("tooldex.scanner.scan_servers", return_value={"a:fs": [_tool_scan_result("t1", [])]}):
            await rescan_server("a:fs")

        updated = get_parser().manifest.get_server("a:fs")
        analyzers = {f["analyzer"] for f in updated.security_findings}
        assert "LLM" in analyzers
        assert "YARA" not in analyzers  # fresh YARA pass found nothing

    @pytest.mark.asyncio
    async def test_skips_yara_when_probe_fails(self):
        server = MCPServer(id="a:fs", name="fs", transport="stdio", command="npx", security_scanned=True)
        _install_manifest({"a:fs": server})
        probe_result = ToolDiscoveryResult(server_id="a:fs", status=ToolDiscoveryStatus.PROTOCOL_ERROR, error="boom")
        with patch("tooldex.core.discovery.tool_discovery.list_tools_for", return_value=probe_result), \
             patch("tooldex.core.discovery.probe_cache.invalidate"), \
             patch("tooldex.scanner.scan_servers") as mock_scan:
            result = await rescan_server("a:fs")

        mock_scan.assert_not_called()
        assert result["security_scanned"] is True  # carried forward untouched, not reset to False

    @pytest.mark.asyncio
    async def test_skips_yara_when_disabled_via_env_var(self, monkeypatch, capsys):
        monkeypatch.setenv("TOOLDEX_SECURITY_SCAN", "false")
        server = MCPServer(id="a:fs", name="fs", transport="stdio", command="npx")
        _install_manifest({"a:fs": server})
        probe_result = ToolDiscoveryResult(
            server_id="a:fs", status=ToolDiscoveryStatus.FOUND,
            tools=[DiscoveredTool(name="t1", server_id="a:fs", description="d")],
        )
        with patch("tooldex.core.discovery.tool_discovery.list_tools_for", return_value=probe_result), \
             patch("tooldex.core.discovery.probe_cache.invalidate"), \
             patch("tooldex.scanner.scan_servers") as mock_scan:
            result = await rescan_server("a:fs")

        mock_scan.assert_not_called()
        assert result["security_scanned"] is False
        assert "Security scan skipped" in capsys.readouterr().out


class TestHealthEndpoint:
    def test_returns_ok(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
