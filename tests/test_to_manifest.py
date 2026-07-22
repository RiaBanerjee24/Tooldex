"""Unit tests for tooldex/core/discovery/to_manifest.py."""
from tooldex.core.discovery.results import (
    ConfigDetectionResult,
    DiscoveredTool,
    ToolDiscoveryResult,
    ToolDiscoveryStatus,
)
from tooldex.core.discovery.to_manifest import build_manifest
from tooldex.core.models.server import MCPServer


def _config_result(*servers: MCPServer) -> ConfigDetectionResult:
    result = ConfigDetectionResult()
    for s in servers:
        result.servers[s.id] = s
    return result


class TestBuildManifest:
    def test_no_tool_results_leaves_servers_unprobed(self):
        config_result = _config_result(MCPServer(id="a:fs", name="fs"))
        manifest = build_manifest(config_result)
        server = manifest.servers["a:fs"]
        assert server.discovered_tools == []
        assert server.probe_status is None
        assert server.probe_error is None

    def test_found_result_populates_tools_and_status(self):
        config_result = _config_result(MCPServer(id="a:fs", name="fs"))
        tool_results = [
            ToolDiscoveryResult(
                server_id="a:fs",
                status=ToolDiscoveryStatus.FOUND,
                tools=[DiscoveredTool(name="read_file", server_id="a:fs", description="reads a file")],
            )
        ]
        manifest = build_manifest(config_result, tool_results)
        server = manifest.servers["a:fs"]
        assert server.probe_status == "found"
        assert server.probe_error is None
        assert len(server.discovered_tools) == 1
        assert server.discovered_tools[0].name == "read_file"

    def test_failed_result_has_no_tools_but_records_error(self):
        config_result = _config_result(MCPServer(id="a:fs", name="fs"))
        tool_results = [
            ToolDiscoveryResult(
                server_id="a:fs",
                status=ToolDiscoveryStatus.CONNECTION_FAILED,
                error="boom",
            )
        ]
        manifest = build_manifest(config_result, tool_results)
        server = manifest.servers["a:fs"]
        assert server.probe_status == "connection_failed"
        assert server.probe_error == "boom"
        assert server.discovered_tools == []

    def test_all_tools_sorted_and_deduplicated(self):
        config_result = _config_result(
            MCPServer(id="a:fs", name="fs"),
            MCPServer(id="b:db", name="db"),
        )
        tool_results = [
            ToolDiscoveryResult(
                server_id="a:fs", status=ToolDiscoveryStatus.FOUND,
                tools=[DiscoveredTool(name="zeta", server_id="a:fs"), DiscoveredTool(name="alpha", server_id="a:fs")],
            ),
            ToolDiscoveryResult(
                server_id="b:db", status=ToolDiscoveryStatus.FOUND,
                tools=[DiscoveredTool(name="alpha", server_id="b:db")],
            ),
        ]
        manifest = build_manifest(config_result, tool_results)
        assert manifest.all_tools == ["alpha", "zeta"]

    def test_server_agents_index_initialized_empty_per_server(self):
        config_result = _config_result(MCPServer(id="a:fs", name="fs"), MCPServer(id="b:db", name="db"))
        manifest = build_manifest(config_result)
        assert manifest.server_agents_index == {"a:fs": [], "b:db": []}

    def test_metadata_name_defaults_to_discovered(self):
        manifest = build_manifest(_config_result())
        assert manifest.metadata.name == "Discovered"

    def test_metadata_name_can_be_overridden(self):
        manifest = build_manifest(_config_result(), name="Custom")
        assert manifest.metadata.name == "Custom"

    def test_original_config_server_left_unmodified(self):
        original = MCPServer(id="a:fs", name="fs")
        config_result = _config_result(original)
        build_manifest(
            config_result,
            [ToolDiscoveryResult(server_id="a:fs", status=ToolDiscoveryStatus.FOUND,
                                  tools=[DiscoveredTool(name="t", server_id="a:fs")])],
        )
        assert original.discovered_tools == []
