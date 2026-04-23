from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field
from pericat.core.models.metadata import PericatMetadata
from pericat.core.models.policy_engine import PolicyEngine
from pericat.core.models.mcp_server import MCPServer
from pericat.core.models.agent_models import Agent
from pericat.core.models.observatory import Observatory
from pericat.core.models.conflict_models import ConflictError, ConflictWarning, OrchestrationIssue
from pericat.core.models.tool_permissions import Tool

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