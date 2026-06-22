from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field


class DiscoveredToolLite(BaseModel):
    """
    Lightweight tool record attached to an MCPServer after autodiscovery.

    Separate from Tool (which carries agent-specific risk/permissions metadata).
    This is neutral: "this tool exists on this server."
    """
    name: str
    description: Optional[str] = None
    input_schema: Optional[dict] = None


class MCPServer(BaseModel):
    """id is the dict key, populated by the parser."""
    id: str = ""
    name: str
    transport: Optional[str] = "stdio"      # "stdio" | "sse" | "streamable-http"
    package: Optional[str] = None
    command: Optional[str] = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    url: Optional[str] = None
    description: Optional[str] = None

    # Populated by autodiscovery (toolpool discover). Empty for YAML-only manifests.
    discovered_tools: list[DiscoveredToolLite] = Field(default_factory=list)

    # Which MCP client config this server was read from (e.g. "claude_code_user",
    # "cursor_project", "docker_mcp:toolpool"). Set by config_detector._merge_servers.
    client: Optional[str] = None

    # Config file this server was read from (e.g. "~/.claude.json")
    source_path: Optional[str] = None
    # For project-scoped servers: the project root directory
    project_path: Optional[str] = None

    # Live connection status derived from the client's CLI.
    # "connected" | "failed" | "needs_auth" | None
    connection_status: Optional[str] = None
    # Raw status string from the CLI — e.g. "not loaded (needs approval)"
    raw_connection_status: Optional[str] = None

    # Result of the last MCP probe attempt.
    # "found" | "empty" | "timeout" | "connection_failed" | "protocol_error" | ...
    # None means the server was never probed (e.g. YAML-only manifest).
    probe_status: Optional[str] = None
    # Human-readable error from the last failed probe, if any.
    probe_error: Optional[str] = None