"""
tooldex/core/discovery/

Autodiscovery sources for tooldex.

Phase 1:
  - config_detector: known config files (Claude Desktop, Claude Code, Cursor, Windsurf)
  - mcp_client:      live `tools/list` probing over stdio
  - tool_discovery:  sync façade for the above

Future phases:
  - ast_scanner:     static scan for MCP URLs and agent definitions
  - crewai_importer: CrewAI agents.yaml import
  - sse / streamable-http transports in mcp_client
"""
from tooldex.core.discovery.config_detector import detect_all
from tooldex.core.discovery.results import (
    ConfigDetectionResult,
    DiscoveredTool,
    DiscoverySource,
    SourceStatus,
    ToolDiscoveryResult,
    ToolDiscoveryStatus,
)
from tooldex.core.discovery.tool_discovery import (
    list_tools_for,
    list_tools_for_all,
)

__all__ = [
    # config_detector
    "ConfigDetectionResult",
    "DiscoverySource",
    "SourceStatus",
    "detect_all",
    # tool discovery
    "DiscoveredTool",
    "ToolDiscoveryResult",
    "ToolDiscoveryStatus",
    "list_tools_for",
    "list_tools_for_all",
]