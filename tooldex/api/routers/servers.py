"""GET /api/servers/, GET /api/servers/{id}/, POST /api/servers/{id}/rescan/"""
import asyncio
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

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


# ---------------------------------------------------------------------------
# LLM-judge job tracking, shared by the llm-scan endpoints and by
# rescan_server / health.rescan_stream to block on or abort a running job.
# ---------------------------------------------------------------------------

@dataclass
class _LlmJudgeJob:
    """Progress/cancellation state for one server's in-flight LLM-judge scan."""
    cancel_event: asyncio.Event
    total: int
    scanned: int = 0
    status: str = "running"  # running | done | stopped | error
    error: Optional[str] = None
    findings_count: int = 0
    security_risk: Optional[str] = None
    task: Optional[asyncio.Task] = None


# server_id -> job, in-memory.
_llm_jobs: dict[str, _LlmJudgeJob] = {}


def llm_job_running(server_id: str) -> bool:
    job = _llm_jobs.get(server_id)
    return bool(job and job.status == "running")


def running_llm_job_ids() -> list[str]:
    return [sid for sid, job in _llm_jobs.items() if job.status == "running"]


async def abort_llm_job(server_id: str, timeout: float = 20.0) -> None:
    """Stop a running LLM-judge job and wait for it to actually finish."""
    job = _llm_jobs.get(server_id)
    if not job or job.status != "running" or job.task is None:
        return
    job.cancel_event.set()
    try:
        await asyncio.wait_for(job.task, timeout=timeout)
    except Exception:
        pass


async def abort_all_llm_jobs() -> None:
    ids = running_llm_job_ids()
    if ids:
        await asyncio.gather(*(abort_llm_job(sid) for sid in ids), return_exceptions=True)


async def _run_llm_judge_job(server_id: str, server, job: _LlmJudgeJob) -> None:
    from datetime import datetime, timezone
    from tooldex.scanner import run_llm_judge_scan
    from tooldex.core.discovery.to_manifest import _security_data, _SEVERITY_RANK

    def on_progress(scanned: int, total: int) -> None:
        job.scanned = scanned
        job.total = total

    try:
        scan_results = await run_llm_judge_scan(
            server, on_progress=on_progress, cancel_event=job.cancel_event
        )
        llm_findings, _ = _security_data(scan_results)

        manifest = get_parser().manifest
        current = manifest.get_server(server_id)
        if current:
            merged = [f for f in current.security_findings if f.get("analyzer") != "LLM"] + llm_findings
            worst = min(
                (f["severity"] for f in merged),
                key=lambda s: _SEVERITY_RANK.get(s.upper(), 99),
                default=None,
            )
            manifest.servers[server_id] = current.model_copy(update={
                "security_findings": merged,
                "security_risk": worst,
                "security_llm_scanned_at": datetime.now(timezone.utc).isoformat(),
                "security_scanned": True,
            })
            job.security_risk = worst

        job.findings_count = len(llm_findings)
        job.status = "stopped" if job.cancel_event.is_set() else "done"
    except Exception as e:
        job.status = "error"
        job.error = str(e)


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
async def llm_scan_server(server_id: str):
    """Start the LLM-as-judge analyzer for one server as a background job. Poll llm-scan/status for progress."""
    manifest = get_parser().manifest
    server = manifest.get_server(server_id)
    if not server:
        raise HTTPException(status_code=404, detail={"error": f"Server '{server_id}' not found"})

    if not server.discovered_tools:
        raise HTTPException(status_code=400, detail={"error": "No discovered tools to scan"})

    existing = _llm_jobs.get(server_id)
    if existing and existing.status == "running":
        return {"status": "running", "scanned": existing.scanned, "total": existing.total}

    job = _LlmJudgeJob(cancel_event=asyncio.Event(), total=len(server.discovered_tools))
    _llm_jobs[server_id] = job
    job.task = asyncio.create_task(_run_llm_judge_job(server_id, server, job))

    return {"status": "started", "total": job.total}


@router.get("/servers/{server_id}/llm-scan/status")
async def llm_scan_status(server_id: str):
    """Poll progress of a running (or just-finished) LLM-judge job for this server."""
    job = _llm_jobs.get(server_id)
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
    job = _llm_jobs.get(server_id)
    if not job or job.status != "running":
        return {"status": job.status if job else "idle"}
    job.cancel_event.set()
    return {"status": "stopping"}
