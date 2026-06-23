"""GET /api/servers/, GET /api/servers/{id}/, POST /api/servers/{id}/rescan/"""
import asyncio
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from tooldex.core.parsers.parser import get_parser, get_last_scanned

router = APIRouter()

_SENSITIVE_HEADERS = frozenset({"authorization", "x-api-key", "x-auth-token", "x-secret"})
_SENSITIVE_ENV_SEGMENTS = frozenset({"key", "secret", "token", "password", "apikey"})


def _is_sensitive_env(name: str) -> bool:
    parts = re.split(r"[_\-]", name.lower())
    return any(p in _SENSITIVE_ENV_SEGMENTS for p in parts)


def _friendly_path(source_path) -> str | None:
    """Return a ~-prefixed path rather than exposing the raw absolute path."""
    if not source_path:
        return None
    try:
        return "~" + str(Path(source_path).relative_to(Path.home()))
    except ValueError:
        return source_path


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

    result = []
    for server_id, server in manifest.servers.items():
        agents_connected = manifest.server_agents_index.get(server_id, [])
        tool_count = len(server.discovered_tools)
        result.append(_redact_server({
            **server.model_dump(),
            "agents_connected": agents_connected,
            "agent_count": len(agents_connected),
            "tool_count": tool_count,
            "discovered_tool_count": tool_count,
            "source_file": _friendly_path(server.source_path),
        }))

    total_tools = sum(len(s.discovered_tools) for s in manifest.servers.values())
    return {
        "servers": result,
        "total": len(result),
        "total_servers": len(result),
        "total_tools": total_tools,
        "scanned_at": get_last_scanned(),
    }


@router.get("/servers/{server_id}")
async def get_server(server_id: str):
    manifest = get_parser().manifest
    server = manifest.get_server(server_id)

    if not server:
        raise HTTPException(
            status_code=404,
            detail={"error": f"Server '{server_id}' not found"},
        )

    agents_connected = manifest.server_agents_index.get(server_id, [])

    return _redact_server({
        **server.model_dump(),
        "agents_connected": agents_connected,
    })


@router.post("/servers/{server_id}/rescan")
async def rescan_server(server_id: str):
    """Re-probe a single server and update its discovered tools in the manifest."""
    from tooldex.core.discovery.tool_discovery import list_tools_for
    from tooldex.core.models.server import DiscoveredToolLite

    manifest = get_parser().manifest
    server = manifest.get_server(server_id)
    if not server:
        raise HTTPException(status_code=404, detail={"error": f"Server '{server_id}' not found"})

    result = await asyncio.to_thread(list_tools_for, server)

    # Re-fetch after the thread in case a full rescan ran concurrently and
    # replaced the manifest. Writing to a stale manifest would be a silent no-op.
    manifest = get_parser().manifest
    server = manifest.get_server(server_id)
    if not server:
        raise HTTPException(status_code=404, detail={"error": f"Server '{server_id}' not found after rescan"})

    new_tools = [
        DiscoveredToolLite(name=t.name, description=t.description, input_schema=t.input_schema)
        for t in result.tools
    ]
    manifest.servers[server_id] = server.model_copy(update={
        "discovered_tools": new_tools,
        "probe_status": result.status.value,
        "probe_error": result.error or None,
    })

    return {
        "status": result.status.value,
        "tool_count": len(new_tools),
        "error": result.error,
        "duration_ms": result.duration_ms,
    }
