"""GET /api/agents, GET /api/agents/{id}"""
from fastapi import APIRouter, HTTPException
from perimeter.core.parser import get_parser

router = APIRouter()


@router.get("/agents")
async def list_agents():
    manifest = get_parser().manifest
    result = []
    for agent in manifest.agents:
        connected_servers = []
        for srv_ref in agent.servers:
            srv = manifest.get_server(srv_ref.ref)
            connected_servers.append({
                "id": srv_ref.ref,
                "name": srv.name if srv else srv_ref.ref,
                "tool_count": len(srv_ref.tools),
            })
        result.append({
            "id": agent.id,
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
        })
    return {"agents": result, "total": len(result)}


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: str):
    manifest = get_parser().manifest
    agent = manifest.get_agent(agent_id)
    if not agent:
        raise HTTPException(
            status_code=404,
            detail={
                "error": f"Agent '{agent_id}' not found in perimeter.yml",
                "available": [a.id for a in manifest.agents],
            }
        )
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
    policy_engine_detail = None
    if agent.policy_engine:
        pe = manifest.get_policy_engine(agent.policy_engine)
        if pe:
            policy_engine_detail = pe.model_dump()
    return {
        "id": agent.id,
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
    }