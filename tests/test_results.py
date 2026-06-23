"""Unit tests for tooldex/core/discovery/results.py."""
from tooldex.core.discovery.results import (
    ConfigDetectionResult,
    DiscoveredTool,
    DiscoverySource,
    SourceStatus,
    ToolDiscoveryResult,
    ToolDiscoveryStatus,
)
from tooldex.core.models.server import MCPServer


class TestToolDiscoveryResult:
    def test_ok_true_when_found(self):
        result = ToolDiscoveryResult(server_id="x", status=ToolDiscoveryStatus.FOUND)
        assert result.ok is True

    def test_ok_false_when_not_found(self):
        result = ToolDiscoveryResult(server_id="x", status=ToolDiscoveryStatus.TIMEOUT)
        assert result.ok is False

    def test_defaults(self):
        result = ToolDiscoveryResult(server_id="x", status=ToolDiscoveryStatus.EMPTY)
        assert result.tools == []
        assert result.error is None
        assert result.duration_ms is None


class TestDiscoverySource:
    def test_ok_true_when_found(self):
        src = DiscoverySource(client="c", path="/p", status=SourceStatus.FOUND)
        assert src.ok is True

    def test_ok_false_when_not_found(self):
        src = DiscoverySource(client="c", path="/p", status=SourceStatus.NOT_FOUND)
        assert src.ok is False

    def test_defaults(self):
        src = DiscoverySource(client="c", path="/p", status=SourceStatus.EMPTY)
        assert src.servers == []
        assert src.error is None
        assert src.in_file_duplicates == []


class TestConfigDetectionResult:
    def test_empty_result_defaults(self):
        result = ConfigDetectionResult()
        assert result.checked == 0
        assert result.found_count == 0
        assert result.error_count == 0
        assert result.server_count == 0

    def test_checked_counts_all_sources(self):
        result = ConfigDetectionResult()
        result.sources.append(DiscoverySource(client="a", path="/a", status=SourceStatus.FOUND))
        result.sources.append(DiscoverySource(client="b", path="/b", status=SourceStatus.NOT_FOUND))
        assert result.checked == 2

    def test_found_count_only_counts_found_status(self):
        result = ConfigDetectionResult()
        result.sources.append(DiscoverySource(client="a", path="/a", status=SourceStatus.FOUND))
        result.sources.append(DiscoverySource(client="b", path="/b", status=SourceStatus.EMPTY))
        assert result.found_count == 1

    def test_error_count_counts_parse_and_read_errors(self):
        result = ConfigDetectionResult()
        result.sources.append(DiscoverySource(client="a", path="/a", status=SourceStatus.PARSE_ERROR))
        result.sources.append(DiscoverySource(client="b", path="/b", status=SourceStatus.READ_ERROR))
        result.sources.append(DiscoverySource(client="c", path="/c", status=SourceStatus.FOUND))
        assert result.error_count == 2

    def test_server_count_reflects_servers_dict(self):
        result = ConfigDetectionResult()
        result.servers["a:fs"] = MCPServer(id="fs", name="fs")
        assert result.server_count == 1

    def test_name_to_qid_not_part_of_equality_or_repr(self):
        result = ConfigDetectionResult()
        result._name_to_qid["fs"] = "a:fs"
        assert "_name_to_qid" not in repr(result)
