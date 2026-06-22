"""GET /api/servers, GET /api/servers/{id}, POST /api/servers/{id}/rescan"""
import asyncio
import re

from fastapi import APIRouter, HTTPException
from toolpool.core.parsers.parser import get_parser, get_last_scanned

router = APIRouter()

_SENSITIVE_HEADERS = frozenset({"authorization", "x-api-key", "x-auth-token", "x-secret"})
_SENSITIVE_ENV_SEGMENTS = frozenset({"key", "secret", "token", "password", "apikey"})


def _is_sensitive_env(name: str) -> bool:
    parts = re.split(r"[_\-]", name.lower())
    return any(p in _SENSITIVE_ENV_SEGMENTS for p in parts)


def _redact_server(d: dict) -> dict:
    """Replace values of sensitive HTTP headers and env vars with '***'."""
    result = dict(d)
    if result.get("headers"):
        result["headers"] = {
            k: "***" if k.lower() in _SENSITIVE_HEADERS else v
            for k, v in result["headers"].items()
        }
    if result.get("env"):
        result["env"] = {
            k: "***" if _is_sensitive_env(k) else v
            for k, v in result["env"].items()
        }
    return result


@router.get("/servers")
async def list_servers():
    manifest = get_parser().manifest
    conflicted = manifest.conflicted_ids("server")
    warned = manifest.warned_ids("server")

    result = []
    for server_id, server in manifest.servers.items():
        # O(1) — precomputed at parse time
        agents_connected = manifest.server_agents_index.get(server_id, [])
        result.append(_redact_server({
            **server.model_dump(),
            "agents_connected": agents_connected,
            "agent_count": len(agents_connected),
            "discovered_tool_count": len(server.discovered_tools),
            "_conflicted": server_id in conflicted,
            "_warned": server_id in warned,
        }))

    return {
        "servers": result,
        "total": len(result),
        "scanned_at": get_last_scanned(),
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
                "error": f"Server '{server_id}' not found in toolpool.yml",
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

    return _redact_server({
        **server.model_dump(),
        "agents_connected": agents_connected,
        "_conflicted": server_id in conflicted,
        "_warned": server_id in warned,
    })


@router.post("/servers/{server_id}/rescan")
async def rescan_server(server_id: str):
    """Re-probe a single server and update its discovered tools in the manifest."""
    from toolpool.core.discovery.tool_discovery import list_tools_for
    from toolpool.core.models.server import DiscoveredToolLite

    manifest = get_parser().manifest
    server = manifest.get_server(server_id)
    if not server:
        raise HTTPException(status_code=404, detail={"error": f"Server '{server_id}' not found"})

    result = await asyncio.to_thread(list_tools_for, server)
    new_tools = [
        DiscoveredToolLite(name=t.name, description=t.description, input_schema=t.input_schema)
        for t in result.tools
    ]
    manifest.servers[server_id] = server.model_copy(update={"discovered_tools": new_tools, "probe_status": result.status.value, "probe_error": result.error or None})

    return {
        "status": result.status.value,
        "tool_count": len(new_tools),
        "error": result.error,
        "duration_ms": result.duration_ms,
    }