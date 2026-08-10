"""POST /api/rescan, GET /api/rescan/stream"""
import asyncio
import json as _json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from tooldex._silenced import silenced as _silenced
from tooldex.core.parsers.parser import store_discovery_sources

router = APIRouter()

_rescan_lock = asyncio.Lock()


@router.post("/rescan")
async def rescan(request: Request):
    """Re-run full MCP discovery and rebuild the manifest."""
    if _rescan_lock.locked():
        return {"status": "already_scanning"}

    async with _rescan_lock:
        from tooldex.core.discovery import detect_all, list_tools_for_all
        from tooldex.core.discovery.to_manifest import build_manifest
        from tooldex.core.parsers.parser import init_parser_from_manifest
        from tooldex._cli_output import print_summary, print_banner
        from tooldex.scanner import scan_servers, security_scan_enabled
        import sys

        try:
            config_result = await asyncio.wait_for(
                asyncio.to_thread(_silenced, detect_all), timeout=120.0
            )
            store_discovery_sources(config_result.sources)
            servers_to_probe = list(config_result.servers.values())
            tool_results = await asyncio.wait_for(
                asyncio.to_thread(
                    _silenced, list_tools_for_all, servers_to_probe,
                ),
                timeout=120.0,
            )
        except asyncio.TimeoutError:
            return {"status": "timeout", "error": "Rescan exceeded 120s limit"}

        if security_scan_enabled():
            probed_ids = {r.server_id for r in tool_results if r.ok}
            scan_targets = {
                sid: srv
                for sid, srv in config_result.servers.items()
                if sid in probed_ids
            }
            scan_results = await asyncio.to_thread(_silenced, scan_servers, scan_targets)
        else:
            # Same env var whether it came from a persisted --no-security-scan or was
            # set directly — no separate "flag" signal survives past process startup.
            print("\n  Security scan skipped — TOOLDEX_SECURITY_SCAN is set to false.", flush=True)
            scan_results = {}

        manifest = build_manifest(config_result, tool_results, scan_results)
        from tooldex.scanner import hydrate_llm_cache
        hydrate_llm_cache(manifest)
        init_parser_from_manifest(manifest)

        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        url = str(request.base_url).rstrip("/")
        print(f"\n── rescan  {ts} ──────────────────────────────────", flush=True)
        print_summary(config_result, tool_results)
        total_tools = sum(len(s.discovered_tools) for s in manifest.servers.values())
        print_banner(len(manifest.servers), total_tools, url)
        sys.stdout.flush()

    return {
        "status": "ok",
        "servers": len(manifest.servers),
        "tools": sum(len(s.discovered_tools) for s in manifest.servers.values()),
    }


@router.get("/rescan/stream")
async def rescan_stream(force: bool = False):
    """
    Stream rescan results as Server-Sent Events, one per server, then a done
    event. Blocked while any LLM-judge job is running unless force=true, in
    which case those jobs are aborted first.

    Event shapes:
      {"type": "blocked", "servers": ["..."]}
      {"type": "result", "server_id": "...", "status": "found"|"...",
       "tool_count": N, "error": null|"...", "duration_ms": N}
      {"type": "done", "total": N, "duration_ms": N}
    """
    from tooldex.core.discovery.mcp_client import probe_server
    from tooldex.core.parsers.parser import get_parser
    from tooldex.core.models.server import DiscoveredToolLite
    from tooldex.api.llm_jobs import running_llm_job_ids, abort_all_llm_jobs

    async def generate():
        running = running_llm_job_ids()
        if running and not force:
            yield f"data: {_json.dumps({'type': 'blocked', 'servers': running})}\n\n"
            return
        if running:
            await abort_all_llm_jobs()

        manifest = get_parser().manifest
        servers = list(manifest.servers.values())

        if not servers:
            yield f"data: {_json.dumps({'type': 'done', 'total': 0, 'duration_ms': 0})}\n\n"
            return

        # Separate concurrency pools: more slots for HTTP, fewer for stdio
        stdio_sem = asyncio.Semaphore(16)
        http_sem  = asyncio.Semaphore(64)
        queue: asyncio.Queue = asyncio.Queue()
        start = asyncio.get_event_loop().time()

        async def probe_one(server):
            transport = (server.transport or "stdio").lower()
            sem = http_sem if transport in ("http", "sse") else stdio_sem
            async with sem:
                result = await probe_server(server)
            await queue.put((server, result))

        tasks = [asyncio.create_task(probe_one(s)) for s in servers]
        manifest_obj = get_parser().manifest

        for _ in range(len(servers)):
            server, result = await queue.get()

            if server.id in manifest_obj.servers:
                new_tools = [
                    DiscoveredToolLite(
                        name=t.name,
                        description=t.description,
                        input_schema=t.input_schema,
                    )
                    for t in result.tools
                ]
                manifest_obj.servers[server.id] = manifest_obj.servers[server.id].model_copy(
                    update={
                        "discovered_tools": new_tools,
                        "probe_status": result.status.value,
                        "probe_error": result.error or None,
                    }
                )

            event = _json.dumps({
                "type": "result",
                "server_id": result.server_id,
                "status": result.status.value,
                "tool_count": len(result.tools),
                "error": result.error,
                "duration_ms": result.duration_ms,
            })
            yield f"data: {event}\n\n"

        await asyncio.gather(*tasks, return_exceptions=True)
        elapsed = int((asyncio.get_event_loop().time() - start) * 1000)
        yield f"data: {_json.dumps({'type': 'done', 'total': len(servers), 'duration_ms': elapsed})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
