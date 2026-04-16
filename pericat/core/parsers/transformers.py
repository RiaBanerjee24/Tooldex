"""
pericat/core/parsers/transformers.py
 
Raw YAML dict → Pydantic model conversions.
No file I/O. No glob resolution. No merge logic.
Pure functions: dict in, model out.
"""
from __future__ import annotations
 
from pericat.core.models import (
    Agent,
    AgentIdentity,
    AgentOrchestration,
    AgentPolicy,
    AgentServerRef,
    FileAccess,
    InlinePolicyRule,
    MCPServer,
    PolicyEngine,
    Tool,
    ToolPermission,
)

 
def parse_tool_permission(raw: dict) -> ToolPermission:
    return ToolPermission(
        operations=raw["operations"],
        on=raw.get("on", "*"),
        access=raw["access"],
    )
 
 
def parse_tool(raw: dict) -> Tool:
    return Tool(
        name=raw["name"],
        description=raw.get("description"),
        risk=raw.get("risk"),
        access=raw.get("access"),
        permissions=[
            parse_tool_permission(p)
            for p in raw.get("permissions", [])
        ],
        denied_by=raw.get("denied_by"),
    )
 
 
def parse_server_ref(raw: dict) -> AgentServerRef:
    return AgentServerRef(
        ref=raw["ref"],
        tools=[parse_tool(t) for t in raw.get("tools", [])],
    )
 
 
def parse_identity(raw: dict) -> AgentIdentity:
    return AgentIdentity(
        type=raw.get("type", "internal"),
        token_lifetime=raw.get("token_lifetime"),
        client_id=raw.get("client_id"),
        scopes=raw.get("scopes", []),
        notes=raw.get("notes"),
    )
 
 
def parse_orchestration(raw: dict) -> AgentOrchestration:
    return AgentOrchestration(
        can_delegate_to=raw.get("can_delegate_to", []),
        receives_from=raw.get("receives_from", []),
    )
 
 
def parse_inline_policy_rule(raw: dict) -> InlinePolicyRule:
    return InlinePolicyRule(
        tool=raw["tool"],
        access=raw["access"],
        reason=raw.get("reason"),
    )
 
 
def parse_agent_policy(raw: dict) -> AgentPolicy:
    return AgentPolicy(
        ref=raw.get("ref"),
        description=raw.get("description"),
        rules=[parse_inline_policy_rule(r) for r in raw.get("rules", [])],
    )
 
 
def parse_agent(agent_id: str, raw: dict, source_file: str) -> Agent:
    agent = Agent(
        id=agent_id,
        name=raw.get("name", agent_id),
        description=raw.get("description"),
        framework=raw.get("framework"),
        status=raw.get("status", "active"),
        owner=raw.get("owner"),
        tags=raw.get("tags", []),
        background=raw.get("background", False),
        identity=parse_identity(raw.get("identity", {})),
        policy_engine=raw.get("policy_engine"),
        servers=[parse_server_ref(s) for s in raw.get("servers", [])],
        file_access=[FileAccess(**f) for f in raw.get("file_access", [])],
        policies=[parse_agent_policy(p) for p in raw.get("policies", [])],
        orchestration=parse_orchestration(raw.get("orchestration", {})),
    )
    agent._source_file = source_file
    return agent
 
 
def parse_server(server_id: str, raw: dict) -> MCPServer:
    return MCPServer(
        id=server_id,
        name=raw.get("name", server_id),
        transport=raw.get("transport", "stdio"),
        package=raw.get("package"),
        command=raw.get("command"),
        args=raw.get("args", []),
        env=raw.get("env", {}),
        url=raw.get("url"),
        description=raw.get("description"),
    )
 
 
def parse_policy_engine(engine_id: str, raw: dict) -> PolicyEngine:
    return PolicyEngine(
        id=engine_id,
        engine=raw["engine"],
        type=raw["type"],
        source=raw["source"],
        description=raw.get("description"),
        policy_path=raw.get("policy_path", "agent.authz.allow"),
    )