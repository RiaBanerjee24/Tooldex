"""GET /api/servers, GET /api/servers/{id}"""
from fastapi import APIRouter, HTTPException
from perimeter.core.parser import get_parser

router = APIRouter()


@router.get("/servers")
async def list_servers():
    manifest = get_parser().manifest
    result = []
    for server in manifest.servers:
        agents_connected = [
            {"id": a.id, "name": a.name}
            for a in manifest.agents
            if any(s.ref == server.id for s in a.servers)
        ]
        result.append({
            **server.model_dump(),
            "agents_connected": agents_connected,
            "agent_count": len(agents_connected),
        })
    return {"servers": result, "total": len(result)}


@router.get("/servers/{server_id}")
async def get_server(server_id: str):
    manifest = get_parser().manifest
    server = manifest.get_server(server_id)
    if not server:
        raise HTTPException(
            status_code=404,
            detail={
                "error": f"Server '{server_id}' not found in perimeter.yml",
                "available": [s.id for s in manifest.servers],
            }
        )
    agents_connected = []
    for agent in manifest.agents:
        srv_ref = next((s for s in agent.servers if s.ref == server_id), None)
        if srv_ref:
            agents_connected.append({
                "id": agent.id,
                "name": agent.name,
                "tools": [
                    {**t.model_dump(), "effective_access": t.effective_access()}
                    for t in srv_ref.tools
                ],
            })
    return {**server.model_dump(), "agents_connected": agents_connected}