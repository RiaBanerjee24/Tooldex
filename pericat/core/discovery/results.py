"""
pericat/core/discovery/results.py

Data containers for discovery results.

A `DiscoverySource` records what happened when Pericat looked at one known
config file (Claude Desktop, Claude Code, Cursor, Windsurf). It's deliberately
verbose — the CLI renders it as a summary so developers can see exactly what
Pericat found, missed, or failed to parse.

A `ConfigDetectionResult` aggregates all sources that were checked plus the
deduplicated list of MCP servers discovered across them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from pericat.core.models.server import MCPServer


# ---------------------------------------------------------------------------
# Tool discovery (live, via MCP tools/list)
# ---------------------------------------------------------------------------

class ToolDiscoveryStatus(str, Enum):
    FOUND = "found"                        # connected, tools/list succeeded
    EMPTY = "empty"                        # connected, but server exposes no tools
    TIMEOUT = "timeout"                    # exceeded configured per-server timeout
    CONNECTION_FAILED = "connection_failed"  # subprocess spawn / pipe setup failed
    PROTOCOL_ERROR = "protocol_error"      # handshake or list_tools raised
    UNSUPPORTED_TRANSPORT = "unsupported_transport"  # e.g. sse when only stdio built
    MISSING_COMMAND = "missing_command"    # stdio server has no `command` field


@dataclass
class DiscoveredTool:
    """
    One tool exposed by an MCP server, as reported by tools/list.

    Separate from pericat.core.models.Tool, which carries
    agent-specific access/risk/permissions metadata. A DiscoveredTool
    is neutral: "this tool exists on this server". The matrix layer
    joins it to agents later.
    """
    name: str
    server_id: str
    description: Optional[str] = None
    input_schema: Optional[dict[str, Any]] = None


@dataclass
class ToolDiscoveryResult:
    """
    Outcome of calling tools/list on one MCPServer.

    `tools` is empty for any status other than FOUND. `error` carries
    human-readable detail for failure statuses — the CLI prints it
    verbatim.
    """
    server_id: str
    status: ToolDiscoveryStatus
    tools: list[DiscoveredTool] = field(default_factory=list)
    error: Optional[str] = None
    duration_ms: Optional[int] = None       # wall time for the probe; None on immediate failures

    @property
    def ok(self) -> bool:
        return self.status == ToolDiscoveryStatus.FOUND


class SourceStatus(str, Enum):
    FOUND = "found"              # file exists, parsed, servers extracted
    NOT_FOUND = "not_found"      # file does not exist at the expected path
    EMPTY = "empty"              # file exists but has no mcpServers block
    PARSE_ERROR = "parse_error"  # file exists but is malformed JSON
    READ_ERROR = "read_error"    # file exists but can't be read (perms etc)


@dataclass
class DiscoverySource:
    """
    Result of checking one known config file.

    `servers` is empty for any status other than FOUND.
    `error` carries human-readable detail for PARSE_ERROR / READ_ERROR.
    """
    client: str                              # "claude_desktop", "cursor", ...
    path: str                                # resolved absolute path that was checked
    status: SourceStatus
    servers: list[MCPServer] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.status == SourceStatus.FOUND


@dataclass
class ConfigDetectionResult:
    """
    Aggregate of every source checked during config-file autodiscovery.

    `servers` is the deduplicated union across sources (same server id →
    first occurrence wins; later sources get dropped with a note attached
    to the DiscoverySource).
    """
    sources: list[DiscoverySource] = field(default_factory=list)
    servers: dict[str, MCPServer] = field(default_factory=dict)
    duplicates: list[str] = field(default_factory=list)  # "cursor:mysql-prod already defined by claude_desktop"

    # ── summary helpers for the CLI ──────────────────────────────────────────

    @property
    def checked(self) -> int:
        return len(self.sources)

    @property
    def found_count(self) -> int:
        return sum(1 for s in self.sources if s.status == SourceStatus.FOUND)

    @property
    def error_count(self) -> int:
        return sum(
            1 for s in self.sources
            if s.status in (SourceStatus.PARSE_ERROR, SourceStatus.READ_ERROR)
        )

    @property
    def server_count(self) -> int:
        return len(self.servers)