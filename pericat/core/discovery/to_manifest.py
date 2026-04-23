"""
pericat/core/discovery/to_manifest.py

Bridge from autodiscovery results → PericatManifest.

The existing parser (parser.py) builds manifests from pericat.yml. This
module builds them from discovery output instead. Both produce the same
PericatManifest shape so the API layer and UI don't care which path the
data came through.

Phase 1 scope: servers + their discovered tools. Agents come later (AST
scanner + CrewAI importer).
"""
from __future__ import annotations

from typing import Optional

from pericat.core.discovery.results import (
    ConfigDetectionResult,
    DiscoveredTool,
    ToolDiscoveryResult,
    ToolDiscoveryStatus,
)
from pericat.core.models.mcp_server import MCPServer, _DiscoveredToolLite
from pericat.core.models.root_manifest import PericatManifest
from pericat.core.models.metadata import PericatMetadata


def build_manifest(
    config_result: ConfigDetectionResult,
    tool_results: Optional[list[ToolDiscoveryResult]] = None,
    name: str = "Discovered",
) -> PericatManifest:
    """
    Build a PericatManifest from autodiscovery output.

    Parameters
    ----------
    config_result
        Output of `detect_all()`. Supplies the MCPServer inventory.
    tool_results
        Optional output of `list_tools_for_all()`. Attaches each server's
        tools via `MCPServer.discovered_tools`. Servers without matching
        tool results simply have an empty tool list.
    name
        Metadata name for the manifest. Shows up in the UI header.

    Notes
    -----
    - `agents` is empty — Phase 1 has no agent discovery yet.
    - Conflict / orchestration fields are all empty by construction —
      autodiscovery can't produce those today.
    - `all_tools` is derived from discovered tools across all servers.
    """
    tool_results = tool_results or []
    tools_by_server = {r.server_id: r for r in tool_results}

    # Attach discovered tools to each server (as pydantic _DiscoveredToolLite).
    servers: dict[str, MCPServer] = {}
    for server_id, server in config_result.servers.items():
        lite_tools = _lite_tools_for(server_id, tools_by_server.get(server_id))
        # Copy the server so we don't mutate the discovery result.
        enriched = server.model_copy(update={"discovered_tools": lite_tools})
        servers[server_id] = enriched

    all_tools = sorted({
        lt.name for server in servers.values() for lt in server.discovered_tools
    })

    return PericatManifest(
        metadata=PericatMetadata(name=name),
        servers=servers,
        agents={},
        all_tools=all_tools,
        agent_tool_index={},
        server_agents_index={sid: [] for sid in servers},
    )


def _lite_tools_for(
    server_id: str,
    result: Optional[ToolDiscoveryResult],
) -> list[_DiscoveredToolLite]:
    """
    Convert a ToolDiscoveryResult → list of _DiscoveredToolLite.

    Returns an empty list for missing, failed, or empty discoveries — the
    caller can look at the raw ToolDiscoveryResult separately if it needs
    to surface errors (the CLI does this).
    """
    if result is None or result.status != ToolDiscoveryStatus.FOUND:
        return []
    return [
        _DiscoveredToolLite(
            name=t.name,
            description=t.description,
            input_schema=t.input_schema,
        )
        for t in result.tools
    ]