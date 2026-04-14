"""
pericat/core/models.py

Pydantic models mapping directly to pericat.yml.
pericat.yml is the single source of truth — no policy engine assumptions.
"""
from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field


class PolicyEngine(BaseModel):
    id: str
    engine: str                               # free label: "opa", "cedar", "casbin", etc.
    type: Literal["file", "http", "inline"]   # how the policy is stored
    source: str                               # file path or URL
    description: Optional[str] = None


class MCPServer(BaseModel):
    id: str
    name: str
    transport: str                            # "stdio", "sse", "streamable-http"
    package: Optional[str] = None
    command: Optional[str] = None
    args: list[str] = []
    env: dict[str, str] = {}
    url: Optional[str] = None
    description: Optional[str] = None


class ToolPermission(BaseModel):
    operations: list[str]
    on: str = "*"
    access: Literal["allowed", "denied"]


class Tool(BaseModel):
    name: str
    description: Optional[str] = None
    risk: Optional[Literal["low", "medium", "high", "critical"]] = None
    access: Optional[Literal["allowed", "denied"]] = None
    permissions: list[ToolPermission] = []
    denied_by: Optional[str] = None

    def effective_access(self) -> str:
        """
        Single access value for the matrix:
        allowed / denied / partial / unknown
        """
        if self.access:
            return self.access
        if not self.permissions:
            return "unknown"
        has_allowed = any(p.access == "allowed" for p in self.permissions)
        has_denied  = any(p.access == "denied"  for p in self.permissions)
        if has_allowed and has_denied:
            return "partial"
        return "allowed" if has_allowed else "denied"


class AgentServerRef(BaseModel):
    ref: str                    # must match servers[].id
    tools: list[Tool] = []


class FileAccess(BaseModel):
    path: str
    permission: str             # "read", "write", "read/write", "denied"
    note: Optional[str] = None


class AgentIdentity(BaseModel):
    type: str                   # "internal", "oauth2", "service_account", "api_key"
    token_lifetime: Optional[str] = None
    client_id: Optional[str] = None
    scopes: list[str] = []
    notes: Optional[str] = None


class InlinePolicyRule(BaseModel):
    tool: str
    access: Literal["allowed", "denied"]
    reason: Optional[str] = None


class AgentPolicy(BaseModel):
    ref: Optional[str] = None           # ref to policy_engines[].id
    description: Optional[str] = None
    rules: list[InlinePolicyRule] = []


class Agent(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    framework: Optional[str] = None
    status: Literal["active", "inactive", "deprecated"] = "active"
    owner: Optional[str] = None
    tags: list[str] = []
    background: bool = False
    identity: AgentIdentity = AgentIdentity(type="internal")
    policy_engine: Optional[str] = None    # ref to policy_engines[].id
    servers: list[AgentServerRef] = []
    file_access: list[FileAccess] = []
    policies: list[AgentPolicy] = []


class Observatory(BaseModel):
    audit_log: str = "./logs/audit.log"
    changes_log: str = "./logs/changes.txt"


class PericatMetadata(BaseModel):
    name: str
    description: Optional[str] = None
    owner: Optional[str] = None
    updated: Optional[str] = None


class PericatManifest(BaseModel):
    pericat: str = Field(default="0.1.0")
    metadata: PericatMetadata
    policy_engines: list[PolicyEngine] = []
    servers: list[MCPServer] = []
    agents: list[Agent] = []
    observatory: Observatory = Observatory()
    model_config = {"populate_by_name": True}

    def get_agent(self, agent_id: str) -> Optional[Agent]:
        return next((a for a in self.agents if a.id == agent_id), None)

    def get_server(self, server_id: str) -> Optional[MCPServer]:
        return next((s for s in self.servers if s.id == server_id), None)

    def get_policy_engine(self, engine_id: str) -> Optional[PolicyEngine]:
        return next((p for p in self.policy_engines if p.id == engine_id), None)

    def all_tools(self) -> list[str]:
        tools: set[str] = set()
        for agent in self.agents:
            for srv in agent.servers:
                for tool in srv.tools:
                    tools.add(tool.name)
        return sorted(tools)

    def agent_tool_access(self, agent_id: str, tool_name: str) -> Optional[Tool]:
        agent = self.get_agent(agent_id)
        if not agent:
            return None
        for srv in agent.servers:
            for tool in srv.tools:
                if tool.name == tool_name:
                    return tool
        return None
