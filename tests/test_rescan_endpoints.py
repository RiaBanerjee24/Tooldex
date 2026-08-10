"""Unit tests for tooldex/api/routers/rescan.py.

These call the route handlers directly (not through TestClient/HTTP) since
their real dependencies (discovery, probing, scanning) are deferred-imported
inside the function bodies and patched at their source modules — this keeps
the tests fast and independent of any real MCP server or subprocess.
"""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from tooldex.api.routers import rescan as rescan_module
from tooldex.core.models.manifest import TooldexManifest, TooldexMetadata
from tooldex.core.models.server import MCPServer
from tooldex.core.parsers.parser import get_parser, init_parser_from_manifest


def _install_manifest(servers):
    manifest = TooldexManifest(metadata=TooldexMetadata(name="Test"), servers=servers)
    init_parser_from_manifest(manifest)
    return manifest


async def _collect_sse(response):
    events = []
    async for chunk in response.body_iterator:
        text = chunk if isinstance(chunk, str) else chunk.decode()
        for line in text.splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[len("data: "):]))
    return events


class TestRescanEndpoint:
    @pytest.mark.asyncio
    async def test_already_scanning_when_lock_held(self):
        async with rescan_module._rescan_lock:
            result = await rescan_module.rescan(SimpleNamespace(base_url="http://test/"))
        assert result == {"status": "already_scanning"}

    @pytest.mark.asyncio
    async def test_successful_rescan_returns_ok_and_installs_manifest(self):
        config_result = SimpleNamespace(sources=[], servers={})
        with patch("tooldex.core.discovery.detect_all", return_value=config_result), \
             patch("tooldex.core.discovery.list_tools_for_all", return_value=[]), \
             patch("tooldex.scanner.scan_servers", return_value={}), \
             patch("tooldex.scanner.hydrate_llm_cache"), \
             patch("tooldex._cli_output.print_summary"), \
             patch("tooldex._cli_output.print_banner"):
            result = await rescan_module.rescan(SimpleNamespace(base_url="http://test/"))

        assert result["status"] == "ok"
        assert result["servers"] == 0
        assert result["tools"] == 0

    @pytest.mark.asyncio
    async def test_security_scan_skipped_when_disabled(self, monkeypatch, capsys):
        monkeypatch.setenv("TOOLDEX_SECURITY_SCAN", "false")
        config_result = SimpleNamespace(sources=[], servers={})
        with patch("tooldex.core.discovery.detect_all", return_value=config_result), \
             patch("tooldex.core.discovery.list_tools_for_all", return_value=[]), \
             patch("tooldex.scanner.scan_servers") as mock_scan, \
             patch("tooldex.scanner.hydrate_llm_cache"), \
             patch("tooldex._cli_output.print_summary"), \
             patch("tooldex._cli_output.print_banner"):
            result = await rescan_module.rescan(SimpleNamespace(base_url="http://test/"))

        assert result["status"] == "ok"
        mock_scan.assert_not_called()
        assert "Security scan skipped" in capsys.readouterr().out

    @pytest.mark.asyncio
    async def test_lock_is_released_after_completion(self):
        config_result = SimpleNamespace(sources=[], servers={})
        with patch("tooldex.core.discovery.detect_all", return_value=config_result), \
             patch("tooldex.core.discovery.list_tools_for_all", return_value=[]), \
             patch("tooldex.scanner.scan_servers", return_value={}), \
             patch("tooldex.scanner.hydrate_llm_cache"), \
             patch("tooldex._cli_output.print_summary"), \
             patch("tooldex._cli_output.print_banner"):
            await rescan_module.rescan(SimpleNamespace(base_url="http://test/"))

        assert rescan_module._rescan_lock.locked() is False


class TestRescanStreamEndpoint:
    @pytest.mark.asyncio
    async def test_blocked_when_llm_job_running_and_not_forced(self):
        _install_manifest({})
        with patch("tooldex.api.llm_jobs.running_llm_job_ids", return_value=["srv:a"]), \
             patch("tooldex.api.llm_jobs.abort_all_llm_jobs", new=AsyncMock()) as mock_abort:
            response = await rescan_module.rescan_stream(force=False)
            events = await _collect_sse(response)

        assert events == [{"type": "blocked", "servers": ["srv:a"]}]
        mock_abort.assert_not_called()

    @pytest.mark.asyncio
    async def test_force_aborts_running_jobs_then_proceeds(self):
        _install_manifest({})
        with patch("tooldex.api.llm_jobs.running_llm_job_ids", return_value=["srv:a"]), \
             patch("tooldex.api.llm_jobs.abort_all_llm_jobs", new=AsyncMock()) as mock_abort:
            response = await rescan_module.rescan_stream(force=True)
            events = await _collect_sse(response)

        mock_abort.assert_called_once()
        assert events[-1]["type"] == "done"
        assert events[-1]["total"] == 0

    @pytest.mark.asyncio
    async def test_no_servers_yields_done_immediately(self):
        _install_manifest({})
        with patch("tooldex.api.llm_jobs.running_llm_job_ids", return_value=[]):
            response = await rescan_module.rescan_stream(force=False)
            events = await _collect_sse(response)

        assert events == [{"type": "done", "total": 0, "duration_ms": 0}]

    @pytest.mark.asyncio
    async def test_probes_each_server_and_yields_result_then_done(self):
        server = MCPServer(id="a:srv", name="srv", transport="stdio")
        _install_manifest({"a:srv": server})

        probe_result = SimpleNamespace(
            server_id="a:srv", status=SimpleNamespace(value="found"),
            tools=[SimpleNamespace(name="t1", description="d", input_schema={})],
            error=None, duration_ms=42,
        )
        with patch("tooldex.api.llm_jobs.running_llm_job_ids", return_value=[]), \
             patch("tooldex.core.discovery.mcp_client.probe_server", new=AsyncMock(return_value=probe_result)):
            response = await rescan_module.rescan_stream(force=False)
            events = await _collect_sse(response)

        result_events = [e for e in events if e["type"] == "result"]
        done_events = [e for e in events if e["type"] == "done"]
        assert len(result_events) == 1
        assert result_events[0]["server_id"] == "a:srv"
        assert result_events[0]["status"] == "found"
        assert result_events[0]["tool_count"] == 1
        assert len(done_events) == 1
        assert done_events[0]["total"] == 1

        updated = get_parser().manifest.get_server("a:srv")
        assert len(updated.discovered_tools) == 1
        assert updated.probe_status == "found"
