from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field
from tooldex.core.models.server import MCPServer


class TooldexMetadata(BaseModel):
    name: str
    description: Optional[str] = None
    owner: Optional[str] = None
    updated: Optional[str] = None


class TooldexManifest(BaseModel):
    metadata: TooldexMetadata
    servers: dict[str, MCPServer] = Field(default_factory=dict)
    all_tools: list[str] = Field(default_factory=list)
    # server_id → [{"id": agent_id, "name": agent_name}] — kept for future agent discovery
    server_agents_index: dict[str, list[dict]] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}

    def get_server(self, server_id: str) -> Optional[MCPServer]:
        return self.servers.get(server_id)
