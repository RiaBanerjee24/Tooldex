"""
pericat/core/models.py

Pydantic models mapping directly to pericat.yml.
pericat.yml is the single source of truth — no policy engine assumptions.
"""
from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Policy engine
# ---------------------------------------------------------------------------
class PolicyEngine(BaseModel):
    """
    id is the dict key in pericat.yml.
    Populated by the parser after loading.
    """
    id: str
    engine: str                               # free label: "opa", "cedar", "casbin", etc.
    type: Literal["file", "http", "inline"]   # how the policy is stored
    source: Optional[str]                               # file path or URL
    description: Optional[str] = None
    policy_path: Optional[str] = "agent.authz.allow"

# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

class MCPServer(BaseModel):
    """
    id is the dict key, populated by parser.
    """
    id: str
    name: Optional[str]
    transport: Optional[str]                            # "stdio", "sse", "streamable-http"
    package: Optional[str] = None
    command: Optional[str] = None
    args: list[str] = []
    env: dict[str, str] = {}
    url: Optional[str] = None
    description: Optional[str] = None

# ---------------------------------------------------------------------------
# Tool permissions
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# Agent server ref
# ---------------------------------------------------------------------------
class AgentServerRef(BaseModel):
    ref: str                    # must match servers[].id
    tools: list[Tool] = []

# ---------------------------------------------------------------------------
# File access
# ---------------------------------------------------------------------------
class FileAccess(BaseModel):
    path: str
    permission: str             # "read", "write", "read/write", "denied"
    note: Optional[str] = None


# ---------------------------------------------------------------------------
# Agent identity
# ---------------------------------------------------------------------------
class AgentIdentity(BaseModel):
    type: str = "internal"                  # "internal", "oauth2", "service_account", "api_key"
    token_lifetime: Optional[str] = None
    client_id: Optional[str] = None
    scopes: list[str] = []
    notes: Optional[str] = None

# ---------------------------------------------------------------------------
# Inline policy
# ---------------------------------------------------------------------------
class InlinePolicyRule(BaseModel):
    tool: str
    access: Literal["allowed", "denied"]
    reason: Optional[str] = None


class AgentPolicy(BaseModel):
    ref: Optional[str] = None           # ref to policy_engines[].id
    description: Optional[str] = None
    rules: list[InlinePolicyRule] = []

# ---------------------------------------------------------------------------
# Orchestration  (A2A delegation)
# ---------------------------------------------------------------------------
class AgentOrchestration(BaseModel):
    """
    can_delegate_to:  this agent may hand off tasks TO these agent ids
    receives_from:    explicitly marks that this agent accepts tasks FROM
                      these agent ids — signals intentional bidirectionality
    """
    can_delegate_to: list[str] = []
    receives_from: list[str] = []

# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------
class Agent(BaseModel):
    """
    id is the dict key, populated by parser.
    """
    id: str = ""
    name: Optional[str]
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
    orchestration: AgentOrchestration = AgentOrchestration()

    # set by parser — which file this agent was loaded from
    _source_file: str = ""

# ---------------------------------------------------------------------------
# Conflict models
# ---------------------------------------------------------------------------
class ConflictError(BaseModel):
    """
    Two included files both define the same id.
    Neither wins — entity is shown as conflicted in UI.
    """
    entity_type: Literal["agent", "server"]
    id: str
    files: list[str]
    message: str

class ConflictWarning(BaseModel):
    """
    Root manifest and an included file both define the same id.
    Root wins. UI shows a warning label on the entity.
    """
    entity_type: Literal["agent", "server"]
    id: str
    winner_file: str       # always the root manifest
    loser_file: str
    message: str

# ---------------------------------------------------------------------------
# Orchestration issue models
# ---------------------------------------------------------------------------
class OrchestrationIssue(BaseModel):
    """
    Detected graph issues across the agent fleet.
 
    type:
      circular     — A → B → A  (two-hop loop, unintentional)
      bidirectional — A → B and B → A but developer used receives_from
                      to signal it's intentional (yellow, not red)
      cycle        — A → B → C → A  (multi-hop loop)
 
    intentional:
      True when every back-edge in the path was declared via receives_from
    """
    type: Literal["circular", "bidirectional", "cycle"]
    agents: list[str]       # agent ids involved
    path: list[str]         # full path e.g. ["router", "read", "router"]
    intentional: bool       # True → yellow warning, False → red warning

# ---------------------------------------------------------------------------
# Observatory
# ---------------------------------------------------------------------------
class Observatory(BaseModel):
    audit_log: str = "./logs/audit.log"
    changes_log: str = "./logs/changes.txt"

# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------
class PericatMetadata(BaseModel):
    name: str
    description: Optional[str] = None
    owner: Optional[str] = None
    updated: Optional[str] = None


class PericatManifest(BaseModel):
    pericat: str = Field(default="0.1.0")
    metadata: PericatMetadata

    # dict key = id
    policy_engines: dict[str, PolicyEngine] = {}
    servers: dict[str, MCPServer] = {}
    agents: dict[str, Agent] = {}

    # include globs / explicit paths (root only)
    include: Optional[list[str]] = None

    observatory: Observatory = Field(default_factory=Observatory)

    # populated by parser after merge
    conflict_errors: list[ConflictError] = Field(default_factory=list)
    conflict_warnings: list[ConflictWarning] = Field(default_factory=list)
    orchestration_issues: list[OrchestrationIssue] = Field(default_factory=list)

    # computed once at parse time by the parser — do not mutate
    all_tools: list[str] = Field(default_factory=list)

    # source files that were loaded (for watch)
    _loaded_files: list[str] = []

    model_config = {"populate_by_name": True}

    def get_agent(self, agent_id: str) -> Optional[Agent]:
        return self.agents.get(agent_id)

    def get_server(self, server_id: str) -> Optional[MCPServer]:
        return self.servers.get(server_id)

    def get_policy_engine(self, engine_id: str) -> Optional[PolicyEngine]:
        return self.policy_engines.get(engine_id)
    
    def agent_tool_access(self, agent_id: str, tool_name: str) -> Optional[Tool]:
        agent = self.get_agent(agent_id)
        if not agent:
            return None
        for srv in agent.servers:
            for tool in srv.tools:
                if tool.name == tool_name:
                    return tool
        return None

    def conflicted_ids(self, entity_type: str) -> set[str]:
        """IDs that are in conflict error state (no data rendered)."""
        return {
            e.id for e in self.conflict_errors
            if e.entity_type == entity_type
        }
    def warned_ids(self, entity_type: str) -> set[str]:
        """IDs that have a conflict warning (root won, show warning label)."""
        return {
            w.id for w in self.conflict_warnings
            if w.entity_type == entity_type
        }
    def has_issues(self) -> bool:
        return bool(
            self.conflict_errors
            or self.conflict_warnings
            or self.orchestration_issues
        )
