"""tooldex/scanner/llm_judge.py — opt-in, per-server LLM-as-judge scan."""
from __future__ import annotations

import asyncio
import logging
import os
import re
from types import SimpleNamespace
from typing import TYPE_CHECKING, Callable

from mcpscanner import Config, Scanner
from mcpscanner.core.models import AnalyzerEnum
from mcpscanner.core.result import ToolScanResult
from mcpscanner.core.scanner import StdioServer

from tooldex.scanner import llm_cache
from tooldex.scanner.config import build_config

if TYPE_CHECKING:
    from tooldex.core.models.server import MCPServer


def _silence_llm_loggers() -> None:
    """Silence LiteLLM and OpenAI client retry noise."""
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

# mcpscanner's LLMAnalyzer.analyze() catches every exception itself (auth
# failures, rate limits, ...), logs it via its own logger
# ("mcpscanner.core.analyzers.base.LLMAnalyzer"), and returns an empty
# findings list — Scanner never sees the exception at all, so a bad key
# would otherwise silently report every remaining tool "safe". Two layers
# guard against that:
#   1. _check_llm_auth   — one real 1-token request before the tool loop
#   2. the per-tool loop — attaches a handler directly to LLMAnalyzer's own
#                          logger to catch a key that dies mid-scan (revoked,
#                          rate-limited); pulls the real status code off the
#                          captured exception object itself (record.exc_info)
#                          rather than pattern-matching the log text, since
#                          the message text isn't guaranteed to contain it
_LLM_STATUS_MESSAGES = {
    400: "LLM provider rejected the request (400) — check TOOLDEX_LLM_MODEL",
    401: "LLM provider rejected the API key (401) — check TOOLDEX_LLM_API_KEY",
    403: "LLM provider denied access (403) — check the API key's permissions",
    404: "LLM provider says the model doesn't exist (404) — check TOOLDEX_LLM_MODEL",
    429: "LLM provider rate limit hit (429) — try again later",
}
_STATUS_CODE_RE = re.compile(r"\b(400|401|403|404|429|500|502|503)\b")


async def _check_llm_auth(config: Config) -> None:
    """One minimal request to confirm the key/model/endpoint actually work,
    before committing to a full per-tool scan."""
    from litellm import acompletion

    is_bedrock = bool(config.llm_model and "bedrock/" in config.llm_model)
    request_params = {
        "model": config.llm_model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1,
        "temperature": config.llm_temperature,
        "timeout": min(config.llm_timeout, 15),
    }
    if config.llm_provider_api_key:
        request_params["api_key"] = config.llm_provider_api_key
    if config.llm_base_url:
        request_params["api_base"] = config.llm_base_url
    if config.llm_api_version:
        request_params["api_version"] = config.llm_api_version
    if is_bedrock:
        if config.aws_region_name:
            request_params["aws_region_name"] = config.aws_region_name
        if config.aws_session_token:
            request_params["aws_session_token"] = config.aws_session_token
        if config.aws_profile_name:
            request_params["aws_profile_name"] = config.aws_profile_name

    try:
        await acompletion(**request_params)
    except Exception as e:
        friendly = _LLM_STATUS_MESSAGES.get(getattr(e, "status_code", None))
        raise ValueError(friendly or f"LLM auth check failed: {e}") from e


class _CaptureLlmErrors(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def _status_error_from_records(records: list[logging.LogRecord]) -> str | None:
    for record in records:
        exc = record.exc_info[1] if record.exc_info else None
        status = getattr(exc, "status_code", None) if exc is not None else None
        if status is not None:
            return _LLM_STATUS_MESSAGES.get(status, f"LLM call failed with status {status}")
        m = _STATUS_CODE_RE.search(record.getMessage())
        if m:
            code = int(m.group(1))
            return _LLM_STATUS_MESSAGES.get(code, f"LLM call failed with status {code}")
    return None


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
    on_cache_hit: Callable[[str], None] | None = None,
    force: bool = False,
) -> list[ToolScanResult]:
    """
    Run the LLM-as-judge analyzer over one server's tools, one at a time
    (throttled by `TOOLDEX_LLM_RATE_LIMIT_DELAY`). Unless `force`, checks
    llm_cache first so unchanged tools reuse their last verdict instead of
    re-calling the LLM — `force=True` (every user-triggered scan) skips that
    read entirely and always makes a real call for every tool, though results
    are still written to the cache either way so page reloads and the next
    `tooldex run` startup can hydrate from them. `on_progress(scanned, total)`
    fires after each tool. `on_cache_hit(tool_name)` fires whenever a tool's
    verdict came from the cache rather than a real call. `cancel_event` stops
    the scan immediately (mid-delay or mid-call) and returns whatever results
    were gathered so far.
    """
    config = build_config()
    if not config.llm_provider_api_key:
        raise ValueError("TOOLDEX_LLM_API_KEY is not configured")

    scanner = Scanner(config)
    delay = config.llm_rate_limit_delay
    tools = list(server.discovered_tools)
    total = len(tools)
    if not total:
        return []

    # Skip the auth check only if every tool is already cache-hit AND we're
    # not forcing — the key won't actually be used this run otherwise.
    needs_real_call = force or any(
        llm_cache.get_cached(
            server.id, t.name, llm_cache.tool_hash(t.name, t.description, t.input_schema)
        ) is None
        for t in tools
    )
    if needs_real_call:
        await _check_llm_auth(config)

    results: list[ToolScanResult] = []
    made_first_call = False
    print(f"[llm-judge] {server.name}: scanning {total} tool(s), ~{delay:.0f}s+ apart" + (" (forced — ignoring cache)" if force else " (unchanged tools reuse their cached verdict)"), flush=True)
    devnull = open(os.devnull, "w")
    try:
        for i, tool in enumerate(tools):
            name = tool.name
            if cancel_event is not None and cancel_event.is_set():
                print(f"[llm-judge] {server.name}: stopped at {i}/{total}", flush=True)
                break

            h = llm_cache.tool_hash(tool.name, tool.description, tool.input_schema)
            cached = None if force else llm_cache.get_cached(server.id, name, h)
            if cached is not None:
                print(f"[llm-judge] {server.name}: [{i + 1}/{total}] {name} — cached, unchanged", flush=True)
                results.append(SimpleNamespace(
                    tool_name=name,
                    is_safe=cached["is_safe"],
                    findings=[SimpleNamespace(**f) for f in cached["findings"]],
                ))
                if on_cache_hit:
                    on_cache_hit(name)
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

            capture = _CaptureLlmErrors()
            # The real error is logged by LLMAnalyzer's own logger (it catches
            # and swallows the exception before Scanner ever sees it); also
            # listen on the scanner logger as defense in depth.
            watched_loggers = [
                logging.getLogger("mcpscanner.core.analyzers.base.LLMAnalyzer"),
                logging.getLogger("mcpscanner.core.scanner"),
            ]
            for lg in watched_loggers:
                lg.addHandler(capture)
            try:
                result = await _race_cancel(scan_coro, cancel_event)
            except Exception as e:
                print(f"[llm-judge] {server.name}: [{i + 1}/{total}] {name} — FAILED: {e}", flush=True)
                result = None
            finally:
                for lg in watched_loggers:
                    lg.removeHandler(capture)

            if result is None and cancel_event is not None and cancel_event.is_set():
                print(f"[llm-judge] {server.name}: stopped mid-scan at [{i + 1}/{total}] {name}", flush=True)
                break

            status_error = _status_error_from_records(capture.records)
            if status_error:
                print(f"[llm-judge] {server.name}: [{i + 1}/{total}] {name} — {status_error}", flush=True)
                raise ValueError(status_error)

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


def hydrate_llm_cache(manifest) -> None:
    """
    Populate each server's LLM-judge state from the persistent cache at
    manifest-build time (tooldex run startup, or a full rebuild), so a
    server judged in a previous session shows its last known verdict
    immediately without requiring a fresh scan. Mutates `manifest` in place.
    """
    from datetime import datetime, timezone
    from tooldex.core.discovery.to_manifest import merge_security_findings

    for server_id, server in list(manifest.servers.items()):
        if not server.discovered_tools:
            continue
        matched = llm_cache.get_all_matching(server_id, server.discovered_tools)
        if not matched:
            continue

        llm_findings = []
        for tool_name, entry in matched.items():
            if not entry["is_safe"]:
                for f in entry["findings"]:
                    llm_findings.append({
                        "tool_name": tool_name,
                        "severity": f["severity"],
                        "analyzer": f["analyzer"],
                        "threat_category": f["threat_category"],
                        "summary": f["summary"],
                    })

        merged, worst = merge_security_findings(server.security_findings, llm_findings)
        latest_ts = max(entry["ts"] for entry in matched.values())

        manifest.servers[server_id] = server.model_copy(update={
            "security_findings": merged,
            "security_risk": worst,
            "security_llm_scanned_at": datetime.fromtimestamp(latest_ts, tz=timezone.utc).isoformat(),
            "security_llm_new_findings": len(llm_findings),
            "security_llm_cache_hits": len(matched),
            "security_llm_last_scan_total": len(matched),
            "security_scanned": True,
        })
