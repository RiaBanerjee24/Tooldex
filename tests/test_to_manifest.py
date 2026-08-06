"""Unit tests for tooldex/core/discovery/to_manifest.py."""
from types import SimpleNamespace

from tooldex.core.discovery.results import (
    ConfigDetectionResult,
    DiscoveredTool,
    ToolDiscoveryResult,
    ToolDiscoveryStatus,
)
from tooldex.core.discovery.to_manifest import _security_data, build_manifest, merge_security_findings
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


def _scan_result(tool_name="t1", severity=None, analyzer="YARA"):
    findings = [] if severity is None else [
        SimpleNamespace(severity=severity, analyzer=analyzer, threat_category="secrets", summary="s")
    ]
    return SimpleNamespace(tool_name=tool_name, is_safe=not findings, findings=findings)


class TestSecurityData:
    def test_no_findings_returns_empty_and_none(self):
        findings, worst = _security_data([_scan_result("t1")])
        assert findings == []
        assert worst is None

    def test_single_finding(self):
        findings, worst = _security_data([_scan_result("t1", "HIGH")])
        assert len(findings) == 1
        assert findings[0]["tool_name"] == "t1"
        assert findings[0]["severity"] == "HIGH"
        assert worst == "HIGH"

    def test_worst_severity_wins_across_multiple_tools(self):
        results = [_scan_result("t1", "LOW"), _scan_result("t2", "CRITICAL")]
        findings, worst = _security_data(results)
        assert len(findings) == 2
        assert worst == "CRITICAL"

    def test_safe_tools_contribute_no_findings(self):
        findings, worst = _security_data([_scan_result("t1"), _scan_result("t2", "MEDIUM")])
        assert len(findings) == 1
        assert worst == "MEDIUM"


class TestMergeSecurityFindings:
    def test_defaults_to_replacing_llm_analyzer(self):
        existing = [
            {"tool_name": "t1", "severity": "HIGH", "analyzer": "YARA"},
            {"tool_name": "t1", "severity": "LOW", "analyzer": "LLM"},
        ]
        new_llm = [{"tool_name": "t1", "severity": "CRITICAL", "analyzer": "LLM"}]
        merged, worst = merge_security_findings(existing, new_llm)
        analyzers = [(f["analyzer"], f["severity"]) for f in merged]
        assert ("YARA", "HIGH") in analyzers
        assert ("LLM", "CRITICAL") in analyzers
        assert ("LLM", "LOW") not in analyzers
        assert worst == "CRITICAL"

    def test_explicit_analyzer_replaces_only_that_analyzer(self):
        existing = [
            {"tool_name": "t1", "severity": "LOW", "analyzer": "YARA"},
            {"tool_name": "t1", "severity": "MEDIUM", "analyzer": "LLM"},
        ]
        fresh_yara = [{"tool_name": "t1", "severity": "CRITICAL", "analyzer": "YARA"}]
        merged, worst = merge_security_findings(existing, fresh_yara, analyzer="YARA")
        analyzers = [(f["analyzer"], f["severity"]) for f in merged]
        assert ("LLM", "MEDIUM") in analyzers  # untouched
        assert ("YARA", "CRITICAL") in analyzers
        assert ("YARA", "LOW") not in analyzers  # replaced
        assert worst == "CRITICAL"

    def test_empty_new_findings_clears_that_analyzer(self):
        existing = [{"tool_name": "t1", "severity": "HIGH", "analyzer": "YARA"}]
        merged, worst = merge_security_findings(existing, [], analyzer="YARA")
        assert merged == []
        assert worst is None

    def test_no_findings_at_all_returns_none_worst(self):
        merged, worst = merge_security_findings([], [])
        assert merged == []
        assert worst is None
