"""Unit tests for tooldex/scanner/yara_scan.py."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from mcpscanner.core.models import AnalyzerEnum

from tooldex.scanner.yara_scan import _scan_one, active_analyzers, scan_servers


def _stdio_server():
    return SimpleNamespace(transport="stdio", command="npx", args=[], env={}, url=None)


def _http_server():
    return SimpleNamespace(transport="http", command=None, url="https://example.com/mcp")


def _unreachable_server():
    return SimpleNamespace(transport="stdio", command=None, url=None)


class TestActiveAnalyzers:
    def test_yara_only(self):
        assert active_analyzers() == [AnalyzerEnum.YARA]

    def test_returns_a_copy_not_the_shared_list(self):
        result = active_analyzers()
        result.append("mutated")
        assert active_analyzers() == [AnalyzerEnum.YARA]


class TestScanServers:
    def test_empty_dict_returns_empty_without_building_scanner(self):
        with patch("tooldex.scanner.yara_scan.build_config") as mock_cfg:
            assert scan_servers({}) == {}
            mock_cfg.assert_not_called()

    def test_aggregates_results_per_server(self):
        scanner_instance = SimpleNamespace(
            scan_stdio_server_tools=AsyncMock(return_value=["finding-a"]),
        )
        with patch("tooldex.scanner.yara_scan.build_config"), \
             patch("tooldex.scanner.yara_scan.Scanner", return_value=scanner_instance):
            result = scan_servers({"srv:a": _stdio_server()})
            assert result == {"srv:a": ["finding-a"]}

    def test_multiple_servers_all_scanned(self):
        scanner_instance = SimpleNamespace(
            scan_stdio_server_tools=AsyncMock(return_value=[]),
            scan_remote_server_tools=AsyncMock(return_value=["remote-finding"]),
        )
        with patch("tooldex.scanner.yara_scan.build_config"), \
             patch("tooldex.scanner.yara_scan.Scanner", return_value=scanner_instance):
            result = scan_servers({"srv:a": _stdio_server(), "srv:b": _http_server()})
            assert result == {"srv:a": [], "srv:b": ["remote-finding"]}


class TestScanOne:
    @pytest.mark.asyncio
    async def test_stdio_server_calls_scan_stdio_server_tools(self):
        scanner = SimpleNamespace(scan_stdio_server_tools=AsyncMock(return_value=["f"]))
        import asyncio
        sid, results = await _scan_one(scanner, "srv:a", _stdio_server(), [AnalyzerEnum.YARA], asyncio.Semaphore(1))
        assert sid == "srv:a"
        assert results == ["f"]

    @pytest.mark.asyncio
    async def test_http_server_calls_scan_remote_server_tools(self):
        scanner = SimpleNamespace(scan_remote_server_tools=AsyncMock(return_value=["r"]))
        import asyncio
        sid, results = await _scan_one(scanner, "srv:b", _http_server(), [AnalyzerEnum.YARA], asyncio.Semaphore(1))
        assert sid == "srv:b"
        assert results == ["r"]

    @pytest.mark.asyncio
    async def test_server_with_neither_command_nor_url_returns_empty(self):
        scanner = SimpleNamespace()
        import asyncio
        sid, results = await _scan_one(scanner, "srv:c", _unreachable_server(), [AnalyzerEnum.YARA], asyncio.Semaphore(1))
        assert sid == "srv:c"
        assert results == []

    @pytest.mark.asyncio
    async def test_scanner_exception_is_swallowed_not_propagated(self):
        scanner = SimpleNamespace(
            scan_stdio_server_tools=AsyncMock(side_effect=RuntimeError("boom")),
        )
        import asyncio
        sid, results = await _scan_one(scanner, "srv:d", _stdio_server(), [AnalyzerEnum.YARA], asyncio.Semaphore(1))
        assert sid == "srv:d"
        assert results == []  # graceful degradation, no raise
