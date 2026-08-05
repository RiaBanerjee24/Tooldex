"""Unit tests for tooldex/core/discovery/tool_discovery.py.

list_tools_for/list_tools_for_all use `_run()`, which creates its own event
loop and explicitly refuses to be called from inside one — so these are
plain sync tests, not @pytest.mark.asyncio (matching how real callers use them).

probe_all/probe_server are real `async def` functions, so patch.object()
auto-creates an AsyncMock for them — its `return_value` is already what the
awaited call resolves to; it must NOT be wrapped in a coroutine manually.
"""
from unittest.mock import patch

import pytest

from tooldex.core.discovery import tool_discovery
from tooldex.core.discovery.results import DiscoveredTool, ToolDiscoveryResult, ToolDiscoveryStatus
from tooldex.core.models.server import DiscoveredToolLite, MCPServer


def _server(id_, **overrides):
    defaults = dict(id=id_, name=id_, command="npx", args=[], transport="stdio")
    defaults.update(overrides)
    return MCPServer(**defaults)


def _found_result(server_id, n_tools=1):
    return ToolDiscoveryResult(
        server_id=server_id,
        status=ToolDiscoveryStatus.FOUND,
        tools=[DiscoveredTool(name=f"t{i}", server_id=server_id) for i in range(n_tools)],
        duration_ms=10,
    )


class TestListToolsFor:
    def test_delegates_to_probe_server(self):
        server = _server("a:x")
        with patch.object(tool_discovery, "probe_server", return_value=_found_result("a:x")):
            result = tool_discovery.list_tools_for(server)
        assert result.server_id == "a:x"
        assert result.ok


class TestListToolsForAll:
    def test_preloaded_servers_get_synthetic_result_without_probing(self):
        server = _server("a:pre", discovered_tools=[DiscoveredToolLite(name="t1", description="d")])
        with patch.object(tool_discovery, "probe_all", return_value=[]) as mock_probe_all:
            results = tool_discovery.list_tools_for_all([server])

        assert len(results) == 1
        assert results[0].server_id == "a:pre"
        assert results[0].status == ToolDiscoveryStatus.FOUND
        assert results[0].tools[0].name == "t1"
        # a fully-preloaded server list means nothing needs a live probe at all
        mock_probe_all.assert_not_called()

    def test_empty_server_list_does_not_call_probe_all(self):
        with patch.object(tool_discovery, "probe_all") as mock_probe_all:
            results = tool_discovery.list_tools_for_all([])
        assert results == []
        mock_probe_all.assert_not_called()

    def test_cache_hit_short_circuits_live_probe(self):
        server = _server("a:cached")
        with patch("tooldex.core.discovery.probe_cache.get_cached", return_value=_found_result("a:cached")), \
             patch.object(tool_discovery, "probe_all") as mock_probe_all:
            results = tool_discovery.list_tools_for_all([server], use_cache=True)

        assert len(results) == 1
        assert results[0].server_id == "a:cached"
        mock_probe_all.assert_not_called()

    def test_cache_miss_probes_live_and_persists_result(self):
        server = _server("a:miss")
        with patch("tooldex.core.discovery.probe_cache.get_cached", return_value=None), \
             patch("tooldex.core.discovery.probe_cache.put_cached") as mock_put, \
             patch.object(tool_discovery, "probe_all", return_value=[_found_result("a:miss")]):
            results = tool_discovery.list_tools_for_all([server], use_cache=True)

        assert len(results) == 1
        assert results[0].server_id == "a:miss"
        mock_put.assert_called_once()

    def test_use_cache_false_always_probes_live(self):
        server = _server("a:x")
        with patch("tooldex.core.discovery.probe_cache.get_cached") as mock_get, \
             patch.object(tool_discovery, "probe_all", return_value=[_found_result("a:x")]) as mock_probe_all:
            tool_discovery.list_tools_for_all([server], use_cache=False)

        mock_get.assert_not_called()
        mock_probe_all.assert_called_once()

    def test_preserves_input_order_across_cached_probed_and_preloaded(self):
        cached_srv = _server("a:cached")
        probed_srv = _server("a:probed")
        preloaded_srv = _server("a:preloaded", discovered_tools=[DiscoveredToolLite(name="t")])
        servers = [preloaded_srv, cached_srv, probed_srv]  # deliberately shuffled

        with patch("tooldex.core.discovery.probe_cache.get_cached", side_effect=lambda s, ttl: _found_result("a:cached") if s.id == "a:cached" else None), \
             patch("tooldex.core.discovery.probe_cache.put_cached"), \
             patch.object(tool_discovery, "probe_all", return_value=[_found_result("a:probed")]):
            results = tool_discovery.list_tools_for_all(servers, use_cache=True)

        assert [r.server_id for r in results] == ["a:preloaded", "a:cached", "a:probed"]


class TestRunRefusesNestedLoop:
    @pytest.mark.asyncio
    async def test_raises_when_called_from_running_loop(self):
        server = _server("a:x")
        with pytest.raises(RuntimeError, match="running event loop"):
            tool_discovery.list_tools_for(server)
