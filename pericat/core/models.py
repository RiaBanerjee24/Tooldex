"""
pericat/core/models.py

Pydantic models mapping to pericat.yml (and included files).

Key changes from v1:
- IDs are now dict keys, not fields (docker-compose style)
- Multi-file support: agents/servers can be split across files
- Orchestration block on agents (A2A delegation)
- Conflict models: ConflictError and ConflictWarning
- OrchestrationIssue: circular, bidirectional, cycle detection
"""
from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Policy engine
# ---------------------------------------------------------------------------

class PolicyEngine(BaseModel):
    """
    id is the dict key in pericat.yml, not a field.
    Populated by the parser after loading.
    """
    id: str = ""
    engine: str                               # "opa", "cedar", "casbin", etc.
    type: Literal["file", "http", "inline"]
    source: str
    description: Optional[str] = None
    policy_path: str = "agent.authz.allow"


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

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
    ref: str                    # must match a server id
    tools: list[Tool] = []


# ---------------------------------------------------------------------------
# File access
# ---------------------------------------------------------------------------

class FileAccess(BaseModel):
    path: str
    permission: str
    note: Optional[str] = None


# ---------------------------------------------------------------------------
# Agent identity
# ---------------------------------------------------------------------------

class AgentIdentity(BaseModel):
    type: str = "internal"
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
    ref: Optional[str] = None
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
    name: str
    description: Optional[str] = None
    framework: Optional[str] = None
    status: Literal["active", "inactive", "deprecated"] = "active"
    owner: Optional[str] = None
    tags: list[str] = []
    background: bool = False
    identity: AgentIdentity = AgentIdentity(type="internal")
    policy_engine: Optional[str] = None
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


# ---------------------------------------------------------------------------
# Root manifest
# ---------------------------------------------------------------------------

class PericatManifest(BaseModel):
    pericat: str = Field(default="0.1.0")
    metadata: PericatMetadata

    # dict key = id
    policy_engines: dict[str, PolicyEngine] = Field(default_factory=dict)
    servers: dict[str, MCPServer] = Field(default_factory=dict)
    agents: dict[str, Agent] = Field(default_factory=dict)

    # include globs / explicit paths (root only) — None means single-file mode
    include: Optional[list[str]] = None

    observatory: Observatory = Field(default_factory=Observatory)

    # populated by parser after merge
    conflict_errors: list[ConflictError] = Field(default_factory=list)
    conflict_warnings: list[ConflictWarning] = Field(default_factory=list)
    orchestration_issues: list[OrchestrationIssue] = Field(default_factory=list)

    # computed once at parse time by the parser — do not mutate
    all_tools: list[str] = Field(default_factory=list)

    # agent_id → {tool_name → Tool}
    # O(1) tool lookup per agent — replaces nested loop in agent_tool_access
    agent_tool_index: dict[str, dict[str, Tool]] = Field(default_factory=dict)

    # server_id → [{"id": agent_id, "name": agent_name}]
    # O(1) agents-by-server lookup — replaces scanning all agents per server
    server_agents_index: dict[str, list[dict]] = Field(default_factory=dict)

    # conflict id sets — precomputed so conflicted_ids/warned_ids are O(1)
    _conflicted_agent_ids: set[str] = set()
    _conflicted_server_ids: set[str] = set()
    _warned_agent_ids: set[str] = set()
    _warned_server_ids: set[str] = set()

    # source files that were loaded (for watch)
    _loaded_files: list[str] = []

    model_config = {"populate_by_name": True}

    # ── convenience lookups — all O(1) ───────────────────────────────────────

    def get_agent(self, agent_id: str) -> Optional[Agent]:
        return self.agents.get(agent_id)

    def get_server(self, server_id: str) -> Optional[MCPServer]:
        return self.servers.get(server_id)

    def get_policy_engine(self, engine_id: str) -> Optional[PolicyEngine]:
        return self.policy_engines.get(engine_id)

    def agent_tool_access(self, agent_id: str, tool_name: str) -> Optional[Tool]:
        """O(1) — uses precomputed agent_tool_index."""
        return self.agent_tool_index.get(agent_id, {}).get(tool_name)

    def conflicted_ids(self, entity_type: str) -> set[str]:
        """O(1) — uses precomputed conflict id sets."""
        if entity_type == "agent":
            return self._conflicted_agent_ids
        if entity_type == "server":
            return self._conflicted_server_ids
        return set()

    def warned_ids(self, entity_type: str) -> set[str]:
        """O(1) — uses precomputed warned id sets."""
        if entity_type == "agent":
            return self._warned_agent_ids
        if entity_type == "server":
            return self._warned_server_ids
        return set()

    def has_issues(self) -> bool:
        return bool(
            self.conflict_errors
            or self.conflict_warnings
            or self.orchestration_issues
        )