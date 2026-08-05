"""tooldex/api/llm_jobs.py — in-memory tracking/cancellation for background LLM-judge scan jobs, one per server."""
import asyncio
from dataclasses import dataclass
from typing import Optional

from tooldex.core.parsers.parser import get_parser


@dataclass
class LlmJudgeJob:
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
_llm_jobs: dict[str, LlmJudgeJob] = {}


def get_job(server_id: str) -> Optional[LlmJudgeJob]:
    return _llm_jobs.get(server_id)


def start_job(server_id: str, job: LlmJudgeJob) -> None:
    _llm_jobs[server_id] = job


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


async def run_llm_judge_job(server_id: str, server, job: LlmJudgeJob, force: bool = False) -> None:
    from datetime import datetime, timezone
    from tooldex.scanner import run_llm_judge_scan
    from tooldex.core.discovery.to_manifest import _security_data, merge_security_findings

    def on_progress(scanned: int, total: int) -> None:
        job.scanned = scanned
        job.total = total

    cache_hit_tools: list[str] = []

    def on_cache_hit(tool_name: str) -> None:
        cache_hit_tools.append(tool_name)

    try:
        scan_results = await run_llm_judge_scan(
            server, on_progress=on_progress, cancel_event=job.cancel_event,
            on_cache_hit=on_cache_hit, force=force,
        )
        llm_findings, _ = _security_data(scan_results)

        manifest = get_parser().manifest
        current = manifest.get_server(server_id)
        if current:
            def finding_key(f):
                return (f.get("tool_name"), f.get("severity"), f.get("threat_category"))

            before = {finding_key(f) for f in current.security_findings if f.get("analyzer") == "LLM"}
            after = {finding_key(f) for f in llm_findings}
            new_count = len(after - before)

            merged, worst = merge_security_findings(current.security_findings, llm_findings)
            manifest.servers[server_id] = current.model_copy(update={
                "security_findings": merged,
                "security_risk": worst,
                "security_llm_scanned_at": datetime.now(timezone.utc).isoformat(),
                "security_llm_new_findings": new_count,
                "security_llm_cache_hits": len(cache_hit_tools),
                "security_llm_last_scan_total": len(scan_results),
                "security_scanned": True,
            })
            job.security_risk = worst

        job.findings_count = len(llm_findings)
        job.status = "stopped" if job.cancel_event.is_set() else "done"
    except Exception as e:
        job.status = "error"
        job.error = str(e)


def has_llm_cache(server_id: str) -> bool:
    from tooldex.scanner import llm_cache
    return llm_cache.has_entries_for(server_id)
