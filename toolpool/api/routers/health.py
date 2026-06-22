"""GET /api/health, POST /api/rescan"""
import asyncio

from fastapi import APIRouter, Request
from toolpool.core.parsers.parser import get_parser
from toolpool import version

router = APIRouter()

_rescan_lock = asyncio.Lock()


def _silenced(fn, *args, **kwargs):
    """Run fn(*args) with stdout+stderr redirected to /dev/null."""
    import os
    devnull = os.open(os.devnull, os.O_WRONLY)
    saved_out, saved_err = os.dup(1), os.dup(2)
    os.dup2(devnull, 1)
    os.dup2(devnull, 2)
    os.close(devnull)
    try:
        return fn(*args, **kwargs)
    finally:
        os.dup2(saved_out, 1); os.close(saved_out)
        os.dup2(saved_err, 2); os.close(saved_err)


@router.post("/rescan")
async def rescan(request: Request):
    """Re-run full MCP discovery and rebuild the manifest."""
    if _rescan_lock.locked():
        return {"status": "already_scanning"}

    async with _rescan_lock:
        from toolpool.core.discovery import detect_all, list_tools_for_all
        from toolpool.core.discovery.to_manifest import build_manifest
        from toolpool.core.parsers.parser import init_parser_from_manifest
        from toolpool._cli_output import print_summary, print_banner
        import sys

        config_result = await asyncio.to_thread(_silenced, detect_all)
        servers_to_probe = list(config_result.servers.values())
        tool_results = await asyncio.to_thread(_silenced, list_tools_for_all, servers_to_probe)
        manifest = build_manifest(config_result, tool_results)
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


@router.get("/health")
async def health():
    parser = get_parser()
    manifest = parser.manifest
    warnings = parser.validate_references()
    return {
        "status": "degraded" if warnings else "ok",
        "toolpool": version,
        "config": {
            "name": manifest.metadata.name,
            "description": manifest.metadata.description,
            "owner": manifest.metadata.owner,
            "updated": manifest.metadata.updated,
            "agents": len(manifest.agents),
            "servers": len(manifest.servers),
            "policy_engines": len(manifest.policy_engines),
        },
        "warnings": warnings,
    }