"""toolpool/core/discovery/to_manifest.py — autodiscovery results → ToolpoolManifest."""
from __future__ import annotations
from typing import Optional

from toolpool.core.discovery.results import (
    ConfigDetectionResult,
    ToolDiscoveryResult,
    ToolDiscoveryStatus,
)
from toolpool.core.models.server import DiscoveredToolLite, MCPServer
from toolpool.core.models.manifest import ToolpoolManifest, ToolpoolMetadata


def build_manifest(
    config_result: ConfigDetectionResult,
    tool_results: Optional[list[ToolDiscoveryResult]] = None,
    name: str = "Discovered",
) -> ToolpoolManifest:
    tool_results = tool_results or []
    tools_by_server = {r.server_id: r for r in tool_results}

    servers: dict[str, MCPServer] = {}
    for server_id, server in config_result.servers.items():
        result = tools_by_server.get(server_id)
        lite_tools = _lite_tools_for(result)
        probe_status = result.status.value if result is not None else None
        probe_error = result.error if (result is not None and result.error) else None
        servers[server_id] = server.model_copy(
            update={"discovered_tools": lite_tools, "probe_status": probe_status, "probe_error": probe_error}
        )

    all_tools = sorted({
        lt.name for server in servers.values() for lt in server.discovered_tools
    })

    return ToolpoolManifest(
        metadata=ToolpoolMetadata(name=name),
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
