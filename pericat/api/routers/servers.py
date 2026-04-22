"""GET /api/servers, GET /api/servers/{id}"""
from fastapi import APIRouter, HTTPException
from pericat.core.parsers.parser import get_parser

router = APIRouter()


@router.get("/servers")
async def list_servers():
    manifest = get_parser().manifest
    conflicted = manifest.conflicted_ids("server")
    warned = manifest.warned_ids("server")

    result = []
    for server_id, server in manifest.servers.items():
        # O(1) — precomputed at parse time
        agents_connected = manifest.server_agents_index.get(server_id, [])
        result.append({
            **server.model_dump(),
            "agents_connected": agents_connected,
            "agent_count": len(agents_connected),
            "discovered_tool_count": len(server.discovered_tools),
            "_conflicted": server_id in conflicted,
            "_warned": server_id in warned,
        })

    return {
        "servers": result,
        "total": len(result),
        "conflict_errors": len([
            e for e in manifest.conflict_errors
            if e.entity_type == "server"
        ]),
    }


@router.get("/servers/{server_id}")
async def get_server(server_id: str):
    manifest = get_parser().manifest
    server = manifest.get_server(server_id)

    if not server:
        conflicted_ids = {e.id for e in manifest.conflict_errors}
        if server_id in conflicted_ids:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": (
                        f"Server '{server_id}' is in conflict — "
                        f"defined in multiple files with no clear winner. "
                        f"Resolve the conflict before accessing this server."
                    ),
                    "conflicts": [
                        e.model_dump() for e in manifest.conflict_errors
                        if e.id == server_id
                    ],
                }
            )
        raise HTTPException(
            status_code=404,
            detail={
                "error": f"Server '{server_id}' not found in pericat.yml",
                "available": list(manifest.servers.keys()),
            }
        )

    # O(1) lookup for which agents connect to this server
    connected_agent_ids = {
        entry["id"]
        for entry in manifest.server_agents_index.get(server_id, [])
    }

    # enrich with tool detail — only for agents that actually connect here
    agents_connected = []
    for agent_id in connected_agent_ids:
        agent = manifest.get_agent(agent_id)
        if not agent:
            continue
        srv_ref = next(
            (s for s in agent.servers if s.ref == server_id), None
        )
        if srv_ref:
            agents_connected.append({
                "id": agent_id,
                "name": agent.name,
                "tools": [
                    {**t.model_dump(), "effective_access": t.effective_access()}
                    for t in srv_ref.tools
                ],
            })

    conflicted = manifest.conflicted_ids("server")
    warned = manifest.warned_ids("server")

    return {
        **server.model_dump(),
        "agents_connected": agents_connected,
        "_conflicted": server_id in conflicted,
        "_warned": server_id in warned,
    }