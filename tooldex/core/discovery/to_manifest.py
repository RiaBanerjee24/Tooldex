"""tooldex/core/discovery/to_manifest.py — autodiscovery results → TooldexManifest."""
from __future__ import annotations
from typing import Optional

from tooldex.core.discovery.results import (
    ConfigDetectionResult,
    ToolDiscoveryResult,
    ToolDiscoveryStatus,
)
from tooldex.core.models.server import DiscoveredToolLite, MCPServer
from tooldex.core.models.manifest import TooldexManifest, TooldexMetadata


def build_manifest(
    config_result: ConfigDetectionResult,
    tool_results: Optional[list[ToolDiscoveryResult]] = None,
    scan_results: Optional[dict] = None,
    name: str = "Discovered",
) -> TooldexManifest:
    tool_results = tool_results or []
    scan_results = scan_results or {}
    tools_by_server = {r.server_id: r for r in tool_results}

    servers: dict[str, MCPServer] = {}
    for server_id, server in config_result.servers.items():
        result = tools_by_server.get(server_id)
        lite_tools = _lite_tools_for(result)
        probe_status = result.status.value if result is not None else None
        probe_error = result.error if (result is not None and result.error) else None
        security_findings, security_risk = _security_data(scan_results.get(server_id, []))
        security_scanned = server_id in scan_results
        servers[server_id] = server.model_copy(
            update={
                "discovered_tools": lite_tools,
                "probe_status": probe_status,
                "probe_error": probe_error,
                "security_findings": security_findings,
                "security_risk": security_risk,
                "security_scanned": security_scanned,
            }
        )

    all_tools = sorted({
        lt.name for server in servers.values() for lt in server.discovered_tools
    })

    return TooldexManifest(
        metadata=TooldexMetadata(name=name),
        servers=servers,
        all_tools=all_tools,
        server_agents_index={sid: [] for sid in servers},
    )


def _lite_tools_for(result: Optional[ToolDiscoveryResult]) -> list[DiscoveredToolLite]:
    if result is None or result.status != ToolDiscoveryStatus.FOUND:
        return []
    return [
        DiscoveredToolLite(name=t.name, description=t.description, input_schema=t.input_schema)
        for t in result.tools
    ]


_SEVERITY_RANK = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}


def _security_data(tool_scan_results: list) -> tuple[list[dict], Optional[str]]:
    """Flatten ToolScanResult list into (findings_dicts, worst_severity)."""
    findings = []
    for t in tool_scan_results:
        if not t.is_safe:
            for f in t.findings:
                findings.append({
                    "tool_name": t.tool_name,
                    "severity": f.severity,
                    "analyzer": f.analyzer,
                    "threat_category": f.threat_category,
                    "summary": f.summary,
                })
    if not findings:
        return [], None
    worst = min(findings, key=lambda f: _SEVERITY_RANK.get(f["severity"].upper(), 99))["severity"]
    return findings, worst


def merge_security_findings(
    existing_findings: list[dict], new_findings: list[dict], analyzer: str = "LLM"
) -> tuple[list[dict], Optional[str]]:
    """Replace a server's `analyzer`-sourced findings with new_findings, leaving other analyzers' findings untouched. Returns (merged, worst_severity)."""
    merged = [f for f in existing_findings if f.get("analyzer") != analyzer] + new_findings
    worst = min(
        (f["severity"] for f in merged),
        key=lambda s: _SEVERITY_RANK.get(s.upper(), 99),
        default=None,
    )
    return merged, worst
