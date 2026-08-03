"""
tooldex/scanner/__init__.py

Security scanning integration using Cisco's mcpscanner library.

YARA runs automatically on every scan. VirusTotal and the LLM judge are
opt-in via env vars; the LLM judge additionally only runs per-server via
run_llm_judge_scan, never automatically.

Env vars:
  VIRUSTOTAL_API_KEY                 — enables VirusTotal binary/package scanning
  MCP_SCANNER_CONCURRENCY            — max servers scanned in parallel (default: 8)
  TOOLDEX_LLM_API_KEY                — enables the per-server LLM judge
  TOOLDEX_LLM_MODEL                  — model to use (e.g. gpt-4o, claude-3-5-sonnet)
  TOOLDEX_LLM_RATE_LIMIT_DELAY       — seconds between LLM calls (default: 2.0)
  TOOLDEX_LLM_TEMPERATURE            — sampling temperature (default: 1.0)
  TOOLDEX_LLM_MAX_RETRIES            — max retries on a failed LLM call (default: 6)
"""
from __future__ import annotations

import asyncio
import logging
import os
from types import SimpleNamespace
from typing import TYPE_CHECKING, Callable

from mcpscanner import Config, Scanner
from mcpscanner.core.models import AnalyzerEnum
from mcpscanner.core.result import ToolScanResult
from mcpscanner.core.scanner import StdioServer

from tooldex.scanner import llm_cache

if TYPE_CHECKING:
    from tooldex.core.models.server import MCPServer

_FREE_ANALYZERS = [
    AnalyzerEnum.YARA,
]

# Silence LiteLLM and OpenAI client retry noise.
def _silence_llm_loggers() -> None:
    try:
        import litellm
        litellm.suppress_debug_info = True
        litellm.set_verbose = False
    except Exception:
        pass
    for name in (
        "LiteLLM", "LiteLLM Router", "LiteLLM Proxy",
        "openai", "openai._base_client", "httpx",
        "mcpscanner", "mcpscanner.core.analyzers.base.LLMAnalyzer",
    ):
        logging.getLogger(name).setLevel(logging.ERROR)


_silence_llm_loggers()


def _build_config() -> Config:
    rate_limit_delay = float(os.getenv("TOOLDEX_LLM_RATE_LIMIT_DELAY", "2.0"))
    max_retries = int(os.getenv("TOOLDEX_LLM_MAX_RETRIES", "6"))
    temperature = float(os.getenv("TOOLDEX_LLM_TEMPERATURE", "1.0"))
    return Config(
        llm_provider_api_key=os.getenv("TOOLDEX_LLM_API_KEY"),
        llm_model=os.getenv("TOOLDEX_LLM_MODEL"),
        llm_rate_limit_delay=rate_limit_delay,
        llm_max_retries=max_retries,
        llm_temperature=temperature,
        virustotal_api_key=os.getenv("VIRUSTOTAL_API_KEY"),
    )


def active_analyzers(config: Config | None = None) -> list[AnalyzerEnum]:
    """Analyzers used by the automatic fleet-wide scan (scan_servers)."""
    if config is None:
        config = _build_config()
    analyzers = list(_FREE_ANALYZERS)
    if config.virustotal_api_key:
        analyzers.append(AnalyzerEnum.VIRUSTOTAL)
    return analyzers


async def _scan_one(
    scanner: Scanner,
    server_id: str,
    server: MCPServer,
    analyzers: list[AnalyzerEnum],
    sem: asyncio.Semaphore,
) -> tuple[str, list[ToolScanResult]]:
    async with sem:
        devnull = open(os.devnull, "w")
        try:
            if server.transport == "stdio" and server.command:
                env = {**os.environ, **(server.env or {})}
                stdio_cfg = StdioServer(
                    command=server.command,
                    args=server.args or [],
                    env=env,
                )
                results = await scanner.scan_stdio_server_tools(
                    stdio_cfg, analyzers=analyzers, errlog=devnull
                )
            elif server.url:
                results = await scanner.scan_remote_server_tools(
                    server.url, analyzers=analyzers
                )
            else:
                results = []
        except Exception:
            results = []
        finally:
            devnull.close()
    return server_id, results


async def _scan_all_async(
    servers: dict[str, MCPServer],
) -> dict[str, list[ToolScanResult]]:
    config = _build_config()
    scanner = Scanner(config)
    analyzers = active_analyzers(config)
    concurrency = int(os.getenv("MCP_SCANNER_CONCURRENCY", "8"))
    sem = asyncio.Semaphore(concurrency)

    pairs = await asyncio.gather(
        *[_scan_one(scanner, sid, srv, analyzers, sem) for sid, srv in servers.items()],
        return_exceptions=True,
    )

    return {
        sid: results
        for item in pairs
        if not isinstance(item, Exception)
        for sid, results in [item]
    }


def scan_servers(
    servers: dict[str, MCPServer],
) -> dict[str, list[ToolScanResult]]:
    """Run the security scan on a set of already-probed servers. Returns server_id -> results."""
    if not servers:
        return {}
    return asyncio.run(_scan_all_async(servers))


async def _race_cancel(coro, cancel_event: asyncio.Event | None):
    """Run `coro` to completion, or cancel it immediately if `cancel_event` fires first."""
    task = asyncio.ensure_future(coro)
    if cancel_event is None:
        return await task
    waiter = asyncio.ensure_future(cancel_event.wait())
    try:
        done, _ = await asyncio.wait({task, waiter}, return_when=asyncio.FIRST_COMPLETED)
        if task in done:
            return task.result()
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
        return None
    finally:
        if not waiter.done():
            waiter.cancel()


async def run_llm_judge_scan(
    server: MCPServer,
    on_progress: Callable[[int, int], None] | None = None,
    cancel_event: asyncio.Event | None = None,
) -> list[ToolScanResult]:
    """
    Run the LLM-as-judge analyzer over one server's tools, one at a time
    (throttled by `TOOLDEX_LLM_RATE_LIMIT_DELAY`), checking llm_cache
    first so unchanged tools reuse their last verdict instead of re-calling
    the LLM. `on_progress(scanned, total)` fires after each tool. `cancel_event`
    stops the scan immediately (mid-delay or mid-call) and returns whatever
    results were gathered so far.
    """
    config = _build_config()
    if not config.llm_provider_api_key:
        raise ValueError("TOOLDEX_LLM_API_KEY is not configured")

    scanner = Scanner(config)
    delay = config.llm_rate_limit_delay
    tools = list(server.discovered_tools)
    total = len(tools)
    if not total:
        return []

    results: list[ToolScanResult] = []
    made_first_call = False
    print(f"[llm-judge] {server.name}: scanning {total} tool(s), ~{delay:.0f}s+ apart (unchanged tools reuse their cached verdict)", flush=True)
    devnull = open(os.devnull, "w")
    try:
        for i, tool in enumerate(tools):
            name = tool.name
            if cancel_event is not None and cancel_event.is_set():
                print(f"[llm-judge] {server.name}: stopped at {i}/{total}", flush=True)
                break

            h = llm_cache.tool_hash(tool.name, tool.description, tool.input_schema)
            cached = llm_cache.get_cached(server.id, name, h)
            if cached is not None:
                print(f"[llm-judge] {server.name}: [{i + 1}/{total}] {name} — cached, unchanged", flush=True)
                results.append(SimpleNamespace(
                    tool_name=name,
                    is_safe=cached["is_safe"],
                    findings=[SimpleNamespace(**f) for f in cached["findings"]],
                ))
                if on_progress:
                    on_progress(i + 1, total)
                continue

            if made_first_call:
                if await _race_cancel(asyncio.sleep(delay), cancel_event) is None and cancel_event is not None and cancel_event.is_set():
                    print(f"[llm-judge] {server.name}: stopped at {i}/{total}", flush=True)
                    break
            made_first_call = True

            print(f"[llm-judge] {server.name}: [{i + 1}/{total}] {name} …", flush=True)
            if server.transport == "stdio" and server.command:
                env = {**os.environ, **(server.env or {})}
                stdio_cfg = StdioServer(
                    command=server.command,
                    args=server.args or [],
                    env=env,
                )
                scan_coro = scanner.scan_stdio_server_tool(
                    stdio_cfg, name, analyzers=[AnalyzerEnum.LLM], errlog=devnull
                )
            elif server.url:
                scan_coro = scanner.scan_remote_server_tool(
                    server.url, name, analyzers=[AnalyzerEnum.LLM]
                )
            else:
                print(f"[llm-judge] {server.name}: [{i + 1}/{total}] {name} — skipped (no command/url)", flush=True)
                if on_progress:
                    on_progress(i + 1, total)
                continue

            try:
                result = await _race_cancel(scan_coro, cancel_event)
            except Exception as e:
                print(f"[llm-judge] {server.name}: [{i + 1}/{total}] {name} — FAILED: {e}", flush=True)
                result = None
            if result is None and cancel_event is not None and cancel_event.is_set():
                print(f"[llm-judge] {server.name}: stopped mid-scan at [{i + 1}/{total}] {name}", flush=True)
                break
            if result is not None:
                results.append(result)
                flat_findings = [
                    {
                        "severity": f.severity,
                        "summary": f.summary,
                        "analyzer": f.analyzer,
                        "threat_category": f.threat_category,
                    }
                    for f in result.findings
                ]
                llm_cache.put_cached(server.id, name, h, flat_findings, result.is_safe)
            if on_progress:
                on_progress(i + 1, total)
    finally:
        devnull.close()

    print(f"[llm-judge] {server.name}: done — {len(results)}/{total} tools scanned", flush=True)
    return results
