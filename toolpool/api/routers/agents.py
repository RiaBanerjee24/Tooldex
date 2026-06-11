"""GET /api/agents, GET /api/agents/{id}"""
from fastapi import APIRouter, HTTPException
from toolpool.core.parsers.parser import get_parser

router = APIRouter()


@router.get("/agents")
async def list_agents():
    manifest = get_parser().manifest

    # -- compute once, lookup O(1) per agent ----------------------------------
    conflicted = manifest.conflicted_ids("agent")
    warned = manifest.warned_ids("agent")

    # pre-index orchestration issues by agent id so we don't scan the full
    # list for every agent (avoids O(agents × issues) loop)
    orch_index: dict[str, list] = {}
    for issue in manifest.orchestration_issues:
        for aid in issue.agents:
            orch_index.setdefault(aid, []).append(issue)

    # -------------------------------------------------------------------------
    result = []
    for agent_id, agent in manifest.agents.items():
        connected_servers = []
        for srv_ref in agent.servers:
            srv = manifest.get_server(srv_ref.ref)
            connected_servers.append({
                "id": srv_ref.ref,
                "name": srv.name if srv else srv_ref.ref,
                "tool_count": len(srv_ref.tools),
            })

        orch = agent.orchestration
        orch_issues = orch_index.get(agent_id, [])

        result.append({
            "id": agent_id,
            "name": agent.name,
            "description": agent.description,
            "framework": agent.framework,
            "status": agent.status,
            "owner": agent.owner,
            "tags": agent.tags,
            "background": agent.background,
            "policy_engine": agent.policy_engine,
            "servers": connected_servers,
            "total_tools": sum(len(s.tools) for s in agent.servers),
            "file_access_count": len(agent.file_access),
            "orchestration": {
                "can_delegate_to": orch.can_delegate_to,
                "receives_from": orch.receives_from,
                "issues": [i.model_dump() for i in orch_issues],
            },
            "_conflicted": agent_id in conflicted,
            "_warned": agent_id in warned,
        })

    return {
        "agents": result,
        "total": len(result),
        "conflict_errors": len(manifest.conflict_errors),
        "conflict_warnings": len(manifest.conflict_warnings),
    }


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: str):
    manifest = get_parser().manifest
    agent = manifest.get_agent(agent_id)

    if not agent:
        # check if it's a conflict error — agent exists but no winner
        conflicted_ids = {e.id for e in manifest.conflict_errors}
        if agent_id in conflicted_ids:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": (
                        f"Agent '{agent_id}' is in conflict — "
                        f"defined in multiple files with no clear winner. "
                        f"Resolve the conflict before accessing this agent."
                    ),
                    "conflicts": [
                        e.model_dump() for e in manifest.conflict_errors
                        if e.id == agent_id
                    ],
                }
            )
        raise HTTPException(
            status_code=404,
            detail={
                "error": f"Agent '{agent_id}' not found in toolpool.yml",
                "available": list(manifest.agents.keys()),
            }
        )

    conflicted = manifest.conflicted_ids("agent")
    warned = manifest.warned_ids("agent")

    # -- servers --------------------------------------------------------------
    resolved_servers = []
    for srv_ref in agent.servers:
        srv = manifest.get_server(srv_ref.ref)
        resolved_servers.append({
            "ref": srv_ref.ref,
            "name": srv.name if srv else srv_ref.ref,
            "transport": srv.transport if srv else None,
            "package": srv.package if srv else None,
            "description": srv.description if srv else None,
            "tools": [
                {**t.model_dump(), "effective_access": t.effective_access()}
                for t in srv_ref.tools
            ],
        })

    # -- policy engine --------------------------------------------------------
    policy_engine_detail = None
    if agent.policy_engine:
        pe = manifest.get_policy_engine(agent.policy_engine)
        if pe:
            policy_engine_detail = pe.model_dump()

    # -- orchestration --------------------------------------------------------
    orch = agent.orchestration

    # single agent lookup — O(issues) is acceptable here
    orch_issues = [
        i.model_dump() for i in manifest.orchestration_issues
        if agent_id in i.agents
    ]

    def resolve_agent_ref(aid: str) -> dict:
        a = manifest.get_agent(aid)
        return {
            "id": aid,
            "name": a.name if a else aid,
            "status": a.status if a else "unknown",
            "_conflicted": aid in conflicted,
        }

    # -------------------------------------------------------------------------
    return {
        "id": agent_id,
        "name": agent.name,
        "description": agent.description,
        "framework": agent.framework,
        "status": agent.status,
        "owner": agent.owner,
        "tags": agent.tags,
        "background": agent.background,
        "identity": agent.identity.model_dump(),
        "policy_engine": policy_engine_detail,
        "servers": resolved_servers,
        "file_access": [f.model_dump() for f in agent.file_access],
        "policies": [p.model_dump() for p in agent.policies],
        "orchestration": {
            "can_delegate_to": [
                resolve_agent_ref(aid) for aid in orch.can_delegate_to
            ],
            "receives_from": [
                resolve_agent_ref(aid) for aid in orch.receives_from
            ],
            "issues": orch_issues,
        },
        "_conflicted": agent_id in conflicted,
        "_warned": agent_id in warned,
    }