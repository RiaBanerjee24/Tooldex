"""GET /api/servers/, GET /api/servers/{id}/, POST /api/servers/{id}/rescan/"""
import asyncio

from fastapi import APIRouter, HTTPException
from tooldex.core.parsers.parser import get_parser, get_last_scanned
from tooldex.api.redact import redact_server, friendly_path
from tooldex.api.llm_jobs import (
    LlmJudgeJob,
    llm_job_running,
    abort_llm_job,
    run_llm_judge_job,
    has_llm_cache,
    get_job,
    start_job,
)

router = APIRouter()


@router.get("/servers")
async def list_servers():
    manifest = get_parser().manifest

    result = []
    for server_id, server in manifest.servers.items():
        agents_connected = manifest.server_agents_index.get(server_id, [])
        tool_count = len(server.discovered_tools)
        result.append(redact_server({
            **server.model_dump(),
            "agents_connected": agents_connected,
            "agent_count": len(agents_connected),
            "tool_count": tool_count,
            "discovered_tool_count": tool_count,
            "source_file": friendly_path(server.source_path),
            "has_llm_cache": has_llm_cache(server_id),
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

    return redact_server({
        **server.model_dump(),
        "agents_connected": agents_connected,
        "has_llm_cache": has_llm_cache(server_id),
    })


@router.post("/servers/{server_id}/rescan")
async def rescan_server(server_id: str, force: bool = False):
    """Re-probe a single server and update its discovered tools. Blocked while an LLM-judge scan is running unless force=true."""
    from tooldex.core.discovery.tool_discovery import list_tools_for
    from tooldex.core.models.server import DiscoveredToolLite

    manifest = get_parser().manifest
    server = manifest.get_server(server_id)
    if not server:
        raise HTTPException(status_code=404, detail={"error": f"Server '{server_id}' not found"})

    if llm_job_running(server_id):
        if not force:
            raise HTTPException(status_code=409, detail={"error": "llm_scan_running"})
        await abort_llm_job(server_id)

    from tooldex.core.discovery.probe_cache import invalidate
    invalidate(server)

    result = await asyncio.to_thread(list_tools_for, server)

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


@router.post("/servers/{server_id}/llm-scan")
async def llm_scan_server(server_id: str, force: bool = True):
    """
    Start the LLM-as-judge analyzer for one server as a background job. Poll
    llm-scan/status for progress. `force` (default true — every UI-triggered
    scan forces fresh calls) skips the per-tool cache and re-judges every
    tool for real; results are still written to the cache either way.
    """
    manifest = get_parser().manifest
    server = manifest.get_server(server_id)
    if not server:
        raise HTTPException(status_code=404, detail={"error": f"Server '{server_id}' not found"})

    if not server.discovered_tools:
        raise HTTPException(status_code=400, detail={"error": "No discovered tools to scan"})

    existing = get_job(server_id)
    if existing and existing.status == "running":
        return {"status": "running", "scanned": existing.scanned, "total": existing.total}

    job = LlmJudgeJob(cancel_event=asyncio.Event(), total=len(server.discovered_tools))
    start_job(server_id, job)
    job.task = asyncio.create_task(run_llm_judge_job(server_id, server, job, force=force))

    return {"status": "started", "total": job.total}


@router.get("/servers/{server_id}/llm-scan/status")
async def llm_scan_status(server_id: str):
    """Poll progress of a running (or just-finished) LLM-judge job for this server."""
    job = get_job(server_id)
    if not job:
        return {"status": "idle"}
    return {
        "status": job.status,
        "scanned": job.scanned,
        "total": job.total,
        "findings_count": job.findings_count,
        "security_risk": job.security_risk,
        "error": job.error,
    }


@router.post("/servers/{server_id}/llm-scan/stop")
async def llm_scan_stop(server_id: str):
    """Signal a running LLM-judge job to stop."""
    job = get_job(server_id)
    if not job or job.status != "running":
        return {"status": job.status if job else "idle"}
    job.cancel_event.set()
    return {"status": "stopping"}


@router.post("/servers/{server_id}/llm-scan/invalidate-cache")
async def llm_scan_invalidate_cache(server_id: str):
    """
    Remove all cached LLM-judge verdicts for this server and reset its
    displayed LLM scan state back to "never scanned" — the cache no longer
    backs those results, so showing them as current would be misleading.
    """
    from tooldex.scanner import llm_cache
    from tooldex.core.discovery.to_manifest import merge_security_findings

    removed = llm_cache.invalidate_server(server_id)

    manifest = get_parser().manifest
    current = manifest.get_server(server_id)
    if current:
        merged, worst = merge_security_findings(current.security_findings, [])
        manifest.servers[server_id] = current.model_copy(update={
            "security_findings": merged,
            "security_risk": worst,
            "security_llm_scanned_at": None,
            "security_llm_new_findings": None,
            "security_llm_cache_hits": None,
            "security_llm_last_scan_total": None,
        })

    return {"status": "ok", "removed": removed}
