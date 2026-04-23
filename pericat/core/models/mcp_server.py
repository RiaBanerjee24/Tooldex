from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field


class _DiscoveredToolLite(BaseModel):
    """
    Pydantic mirror of pericat.core.discovery.DiscoveredTool.

    Kept in models.py so MCPServer can reference it without a circular
    import from discovery/. Converted to/from the dataclass version at
    the discovery/manifest boundary.
    """
    name: str
    description: Optional[str] = None
    input_schema: Optional[dict] = None


class MCPServer(BaseModel):
    """
    id is the dict key, populated by parser.
    """
    id: str = ""
    name: str
    transport: Optional[str] = "stdio"        # "stdio", "sse", "streamable-http"
    package: Optional[str] = None
    command: Optional[str] = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: Optional[str] = None
    description: Optional[str] = None

    # Populated by autodiscovery (pericat discover). Neutral "this server
    # exposes these tools" info — separate from per-agent access metadata
    # which lives on AgentServerRef.tools. Empty for YAML-only manifests.
    discovered_tools: list["_DiscoveredToolLite"] = Field(default_factory=list)