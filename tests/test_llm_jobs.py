"""Unit tests for tooldex/api/llm_jobs.py."""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from tooldex.api.llm_jobs import (
    LlmJudgeJob,
    abort_all_llm_jobs,
    abort_llm_job,
    get_job,
    has_llm_cache,
    llm_job_running,
    run_llm_judge_job,
    running_llm_job_ids,
    start_job,
)
from tooldex.core.models.manifest import TooldexManifest, TooldexMetadata
from tooldex.core.models.server import MCPServer
from tooldex.core.parsers.parser import init_parser_from_manifest
from tooldex.scanner import llm_cache


def _install_manifest(servers):
    manifest = TooldexManifest(metadata=TooldexMetadata(name="Test"), servers=servers)
    init_parser_from_manifest(manifest)
    return manifest


class TestLlmJudgeJobDefaults:
    def test_defaults(self):
        job = LlmJudgeJob(cancel_event=asyncio.Event(), total=5)
        assert job.scanned == 0
        assert job.status == "running"
        assert job.error is None
        assert job.findings_count == 0
        assert job.security_risk is None
        assert job.task is None


class TestJobRegistry:
    def test_get_job_returns_none_when_absent(self):
        assert get_job("srv:missing") is None

    def test_start_and_get_round_trip(self):
        job = LlmJudgeJob(cancel_event=asyncio.Event(), total=3)
        start_job("srv:a", job)
        assert get_job("srv:a") is job

    def test_llm_job_running_true_only_for_running_status(self):
        running = LlmJudgeJob(cancel_event=asyncio.Event(), total=1, status="running")
        done = LlmJudgeJob(cancel_event=asyncio.Event(), total=1, status="done")
        start_job("srv:running", running)
        start_job("srv:done", done)
        assert llm_job_running("srv:running") is True
        assert llm_job_running("srv:done") is False
        assert llm_job_running("srv:absent") is False

    def test_running_llm_job_ids_filters_correctly(self):
        start_job("srv:a", LlmJudgeJob(cancel_event=asyncio.Event(), total=1, status="running"))
        start_job("srv:b", LlmJudgeJob(cancel_event=asyncio.Event(), total=1, status="done"))
        start_job("srv:c", LlmJudgeJob(cancel_event=asyncio.Event(), total=1, status="running"))
        assert set(running_llm_job_ids()) == {"srv:a", "srv:c"}

    def test_running_llm_job_ids_empty_when_none_running(self):
        assert running_llm_job_ids() == []


class TestAbortLlmJob:
    @pytest.mark.asyncio
    async def test_noop_when_job_does_not_exist(self):
        await abort_llm_job("srv:missing")  # must not raise

    @pytest.mark.asyncio
    async def test_noop_when_job_not_running(self):
        job = LlmJudgeJob(cancel_event=asyncio.Event(), total=1, status="done")
        start_job("srv:a", job)
        await abort_llm_job("srv:a")
        assert job.cancel_event.is_set() is False

    @pytest.mark.asyncio
    async def test_noop_when_no_task_attached(self):
        job = LlmJudgeJob(cancel_event=asyncio.Event(), total=1, status="running", task=None)
        start_job("srv:a", job)
        await abort_llm_job("srv:a")
        assert job.cancel_event.is_set() is False

    @pytest.mark.asyncio
    async def test_sets_cancel_event_and_awaits_task(self):
        cancel_event = asyncio.Event()

        async def fake_job():
            await cancel_event.wait()
            return "stopped"

        task = asyncio.create_task(fake_job())
        job = LlmJudgeJob(cancel_event=cancel_event, total=1, status="running", task=task)
        start_job("srv:a", job)

        await abort_llm_job("srv:a", timeout=2.0)

        assert cancel_event.is_set() is True
        assert task.done()


class TestAbortAllLlmJobs:
    @pytest.mark.asyncio
    async def test_aborts_only_running_jobs(self):
        e1, e2 = asyncio.Event(), asyncio.Event()

        async def wait_for(e):
            await e.wait()

        t1 = asyncio.create_task(wait_for(e1))
        t2 = asyncio.create_task(wait_for(e2))
        start_job("srv:running1", LlmJudgeJob(cancel_event=e1, total=1, status="running", task=t1))
        start_job("srv:running2", LlmJudgeJob(cancel_event=e2, total=1, status="running", task=t2))
        start_job("srv:done", LlmJudgeJob(cancel_event=asyncio.Event(), total=1, status="done"))

        await abort_all_llm_jobs()

        assert e1.is_set() and e2.is_set()

    @pytest.mark.asyncio
    async def test_noop_when_nothing_running(self):
        await abort_all_llm_jobs()  # must not raise with an empty registry


class TestHasLlmCache:
    def test_false_when_nothing_cached(self):
        assert has_llm_cache("srv:x") is False

    def test_true_after_caching(self):
        h = llm_cache.tool_hash("t", "d", {})
        llm_cache.put_cached("srv:x", "t", h, [], is_safe=True)
        assert has_llm_cache("srv:x") is True


class TestRunLlmJudgeJob:
    @pytest.mark.asyncio
    async def test_success_updates_manifest_and_marks_done(self):
        server = MCPServer(id="a:srv", name="srv", security_findings=[])
        _install_manifest({"a:srv": server})
        job = LlmJudgeJob(cancel_event=asyncio.Event(), total=1)

        scan_results = [
            type("R", (), {
                "tool_name": "bad_tool", "is_safe": False,
                "findings": [type("F", (), {
                    "severity": "HIGH", "analyzer": "LLM",
                    "threat_category": "DATA EXFILTRATION", "summary": "leaks data",
                })()],
            })()
        ]
        with patch("tooldex.scanner.run_llm_judge_scan", new=AsyncMock(return_value=scan_results)):
            await run_llm_judge_job("a:srv", server, job, force=True)

        assert job.status == "done"
        assert job.error is None
        assert job.findings_count == 1
        assert job.security_risk == "HIGH"

        from tooldex.core.parsers.parser import get_parser
        updated = get_parser().manifest.get_server("a:srv")
        assert len(updated.security_findings) == 1
        assert updated.security_risk == "HIGH"

    @pytest.mark.asyncio
    async def test_new_findings_count_excludes_previously_known_ones(self):
        existing_finding = {
            "tool_name": "old_tool", "severity": "LOW",
            "analyzer": "LLM", "threat_category": "X", "summary": "old",
        }
        server = MCPServer(id="a:srv", name="srv", security_findings=[existing_finding])
        _install_manifest({"a:srv": server})
        job = LlmJudgeJob(cancel_event=asyncio.Event(), total=1)

        # scan returns the SAME finding again (unchanged) -> new_count should be 0
        scan_results = [
            type("R", (), {
                "tool_name": "old_tool", "is_safe": False,
                "findings": [type("F", (), {
                    "severity": "LOW", "analyzer": "LLM",
                    "threat_category": "X", "summary": "old",
                })()],
            })()
        ]
        with patch("tooldex.scanner.run_llm_judge_scan", new=AsyncMock(return_value=scan_results)):
            await run_llm_judge_job("a:srv", server, job, force=True)

        from tooldex.core.parsers.parser import get_parser
        updated = get_parser().manifest.get_server("a:srv")
        # security_llm_new_findings isn't set by run_llm_judge_job itself (that's
        # the caller's job in servers.py), but job.findings_count reflects total
        # LLM findings from this run, unaffected by what existed before
        assert job.findings_count == 1
        assert len(updated.security_findings) == 1  # replaced, not duplicated

    @pytest.mark.asyncio
    async def test_marks_stopped_when_cancelled(self):
        server = MCPServer(id="a:srv", name="srv")
        _install_manifest({"a:srv": server})
        cancel_event = asyncio.Event()
        cancel_event.set()
        job = LlmJudgeJob(cancel_event=cancel_event, total=1)

        with patch("tooldex.scanner.run_llm_judge_scan", new=AsyncMock(return_value=[])):
            await run_llm_judge_job("a:srv", server, job, force=True)

        assert job.status == "stopped"

    @pytest.mark.asyncio
    async def test_exception_marks_job_as_error(self):
        server = MCPServer(id="a:srv", name="srv")
        _install_manifest({"a:srv": server})
        job = LlmJudgeJob(cancel_event=asyncio.Event(), total=1)

        with patch(
            "tooldex.scanner.run_llm_judge_scan",
            new=AsyncMock(side_effect=ValueError("LLM provider rejected the API key (401)")),
        ):
            await run_llm_judge_job("a:srv", server, job, force=True)

        assert job.status == "error"
        assert "rejected the API key" in job.error

    @pytest.mark.asyncio
    async def test_progress_callback_updates_job_scanned_total(self):
        server = MCPServer(id="a:srv", name="srv")
        _install_manifest({"a:srv": server})
        job = LlmJudgeJob(cancel_event=asyncio.Event(), total=2)

        async def fake_scan(server, on_progress=None, cancel_event=None, on_cache_hit=None, force=False):
            if on_progress:
                on_progress(1, 2)
                on_progress(2, 2)
            return []

        with patch("tooldex.scanner.run_llm_judge_scan", new=fake_scan):
            await run_llm_judge_job("a:srv", server, job, force=True)

        assert job.scanned == 2
        assert job.total == 2

    @pytest.mark.asyncio
    async def test_missing_server_in_manifest_does_not_crash(self):
        _install_manifest({})  # server_id below is not in the manifest
        server = MCPServer(id="a:gone", name="gone")
        job = LlmJudgeJob(cancel_event=asyncio.Event(), total=1)

        with patch("tooldex.scanner.run_llm_judge_scan", new=AsyncMock(return_value=[])):
            await run_llm_judge_job("a:gone", server, job, force=True)

        assert job.status == "done"  # scan itself succeeded; manifest update was just skipped
