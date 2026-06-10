"""
GET /api/policy/matrix
GET /api/policy/engines
GET /api/policy/engines/{id}/raw
"""
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pericat.core.parsers.parser import get_parser

router = APIRouter()


@router.get("/policy/matrix")
async def policy_matrix():
    manifest = get_parser().manifest
    tools = manifest.all_tools
    conflicted_agents = manifest.conflicted_ids("agent")
    warned_agents = manifest.warned_ids("agent")
    matrix = {}

    for agent_id, agent in manifest.agents.items():
        if agent_id in conflicted_agents:
            matrix[agent_id] = {
                "agent_name": agent_id,
                "policy_engine": None,
                "tools": {},
                "_conflicted": True,
                "_warned": False,
            }
            continue

        agent_tools = {}
        for tool_name in tools:
            tool = manifest.agent_tool_access(agent_id, tool_name)
            if tool is None:
                agent_tools[tool_name] = {
                    "effective_access": "not_configured",
                    "access": None,
                    "risk": None,
                    "permissions": [],
                    "denied_by": None,
                }
            else:
                agent_tools[tool_name] = {
                    "effective_access": tool.effective_access(),
                    "access": tool.access,
                    "risk": tool.risk,
                    "permissions": [p.model_dump() for p in tool.permissions],
                    "denied_by": tool.denied_by,
                }

        matrix[agent_id] = {
            "agent_name": agent.name,
            "policy_engine": agent.policy_engine,
            "tools": agent_tools,
            "_conflicted": False,
            "_warned": agent_id in warned_agents,
        }

    return {
        "matrix": matrix,
        "tools": tools,
        "agents": [
            {
                "id": aid,
                "name": a.name,
                "_conflicted": aid in conflicted_agents,
                "_warned": aid in warned_agents,
            }
            for aid, a in manifest.agents.items()
        ],
    }


@router.get("/policy/engines")
async def list_engines():
    manifest = get_parser().manifest
    return {
        "engines": {eid: pe.model_dump() for eid, pe in manifest.policy_engines.items()},
        "total": len(manifest.policy_engines),
    }


@router.get("/policy/engines/{engine_id}/raw")
async def get_raw_policy(engine_id: str):
    manifest = get_parser().manifest
    pe = manifest.get_policy_engine(engine_id)
    if not pe:
        raise HTTPException(
            status_code=404,
            detail={
                "error": f"Policy engine '{engine_id}' not found",
                "available": list(manifest.policy_engines.keys()),
            }
        )
    if pe.type != "file":
        raise HTTPException(
            status_code=400,
            detail=(
                f"Engine '{engine_id}' is type='{pe.type}'. "
                f"Only type='file' supports raw content."
            )
        )
    path = Path(pe.source)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Policy file not found: {pe.source}")
    return {
        "engine_id": engine_id,
        "engine": pe.engine,
        "source": pe.source,
        "content": path.read_text(),
    }
