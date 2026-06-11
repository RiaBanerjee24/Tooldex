"""GET /api/conflicts, GET /api/orchestration"""
from fastapi import APIRouter
from toolpool.core.parsers.parser import get_parser

router = APIRouter()


@router.get("/conflicts")
async def list_conflicts():
    manifest = get_parser().manifest
    return {
        "errors": [e.model_dump() for e in manifest.conflict_errors],
        "warnings": [w.model_dump() for w in manifest.conflict_warnings],
        "total_errors": len(manifest.conflict_errors),
        "total_warnings": len(manifest.conflict_warnings),
        "has_issues": manifest.has_issues(),
    }


@router.get("/orchestration")
async def orchestration_overview():
    manifest = get_parser().manifest
    conflicted = manifest.conflicted_ids("agent")

    edges = []
    for agent_id, agent in manifest.agents.items():
        if agent_id in conflicted:
            continue
        for target in agent.orchestration.can_delegate_to:
            target_agent = manifest.get_agent(target)
            intentional = (
                target_agent is not None
                and agent_id in target_agent.orchestration.receives_from
            )
            edges.append({"from": agent_id, "to": target, "intentional": intentional})

    issues = manifest.orchestration_issues

    return {
        "edges": edges,
        "issues": [i.model_dump() for i in issues],
        "total_issues": len(issues),
        "circular_count": sum(1 for i in issues if i.type == "circular"),
        "bidirectional_count": sum(1 for i in issues if i.type == "bidirectional"),
        "cycle_count": sum(1 for i in issues if i.type == "cycle"),
        "agents": [
            {
                "id": aid,
                "name": a.name,
                "can_delegate_to": a.orchestration.can_delegate_to,
                "receives_from": a.orchestration.receives_from,
            }
            for aid, a in manifest.agents.items()
            if aid not in conflicted
        ],
    }
