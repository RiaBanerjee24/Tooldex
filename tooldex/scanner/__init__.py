"""
tooldex/scanner/__init__.py

Security scanning integration using Cisco's mcpscanner library.

YARA runs automatically on every scan. The LLM judge (run_llm_judge_scan
below) is opt-in, per-server only, triggered manually — never as part of
the automatic fleet-wide scan.

Env vars:
  MCP_SCANNER_CONCURRENCY            — max servers scanned in parallel (default: 8)
  TOOLDEX_LLM_API_KEY                — enables the per-server LLM judge
  TOOLDEX_LLM_MODEL                  — model to use (e.g. gpt-4o, claude-3-5-sonnet)
  TOOLDEX_LLM_RATE_LIMIT_DELAY       — seconds between LLM calls (default: 2.0)
  TOOLDEX_LLM_TEMPERATURE            — sampling temperature (default: 1.0)
  TOOLDEX_LLM_MAX_RETRIES            — max retries on a failed LLM call (default: 6)
  TOOLDEX_LLM_BASE_URL               — custom endpoint (Azure OpenAI, local Ollama/vLLM/LocalAI, etc.)
  TOOLDEX_LLM_API_VERSION            — API version, e.g. for Azure OpenAI
  TOOLDEX_LLM_TIMEOUT                — per-request LLM timeout in seconds (default: 30)

Each of the above also accepts its original mcpscanner name
(MCP_SCANNER_LLM_*) as a fallback if the TOOLDEX_LLM_* one isn't set — see
_env_with_legacy_fallback — so an existing mcpscanner-native setup keeps
working un-migrated, with a one-time bright-yellow CLI notice pointing at
the rename.
"""
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

# Scanner.scan_stdio_server_tool(s)/scan_remote_server_tool(s) swallow LLM
# call failures internally (log an ERROR, then treat the tool as having no
# findings) — a bad key would otherwise silently report every tool "safe".
# Two layers guard against that:
#   1. _check_llm_auth   — one real 1-token request before the tool loop
#   2. the per-tool loop — captures mcpscanner's own error logging to catch
#                          a key that dies mid-scan (revoked, rate-limited)
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
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def _status_error_from_logs(messages: list[str]) -> str | None:
    for msg in messages:
        m = _STATUS_CODE_RE.search(msg)
        if m:
            code = int(m.group(1))
            return _LLM_STATUS_MESSAGES.get(code, f"LLM call failed with status {code}")
    return None


_warned_legacy_llm_vars: set[str] = set()


def _env_with_legacy_fallback(new_name: str, legacy_name: str) -> str | None:
    """
    Read `new_name`, falling back to mcpscanner's original `legacy_name` if
    unset — so an existing mcpscanner-native setup keeps working un-migrated.
    Prints a one-time bright-yellow CLI notice the first time a fallback is
    actually used.
    """
    value = os.getenv(new_name)
    if value is not None:
        return value
    legacy_value = os.getenv(legacy_name)
    if legacy_value is not None and legacy_name not in _warned_legacy_llm_vars:
        _warned_legacy_llm_vars.add(legacy_name)
        print(
            f"\033[93m[tooldex] {legacy_name} is set but {new_name} is not — "
            f"using {legacy_name} for now. Rename it to {new_name}.\033[0m",
            flush=True,
        )
    return legacy_value


def _build_config() -> Config:
    rate_limit_delay = float(_env_with_legacy_fallback("TOOLDEX_LLM_RATE_LIMIT_DELAY", "MCP_SCANNER_LLM_RATE_LIMIT_DELAY") or "2.0")
    max_retries = int(_env_with_legacy_fallback("TOOLDEX_LLM_MAX_RETRIES", "MCP_SCANNER_LLM_MAX_RETRIES") or "6")
    temperature = float(_env_with_legacy_fallback("TOOLDEX_LLM_TEMPERATURE", "MCP_SCANNER_LLM_TEMPERATURE") or "1.0")
    timeout = _env_with_legacy_fallback("TOOLDEX_LLM_TIMEOUT", "MCP_SCANNER_LLM_TIMEOUT")
    return Config(
        llm_provider_api_key=_env_with_legacy_fallback("TOOLDEX_LLM_API_KEY", "MCP_SCANNER_LLM_API_KEY"),
        llm_model=_env_with_legacy_fallback("TOOLDEX_LLM_MODEL", "MCP_SCANNER_LLM_MODEL"),
        llm_rate_limit_delay=rate_limit_delay,
        llm_max_retries=max_retries,
        llm_temperature=temperature,
        llm_base_url=_env_with_legacy_fallback("TOOLDEX_LLM_BASE_URL", "MCP_SCANNER_LLM_BASE_URL"),
        llm_api_version=_env_with_legacy_fallback("TOOLDEX_LLM_API_VERSION", "MCP_SCANNER_LLM_API_VERSION"),
        llm_timeout=float(timeout) if timeout else None,
    )


def active_analyzers() -> list[AnalyzerEnum]:
    """Analyzers used by the automatic fleet-wide scan (scan_servers)."""
    return list(_FREE_ANALYZERS)


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
    analyzers = active_analyzers()
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
    config = _build_config()
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
            scanner_logger = logging.getLogger("mcpscanner.core.scanner")
            scanner_logger.addHandler(capture)
            try:
                result = await _race_cancel(scan_coro, cancel_event)
            except Exception as e:
                print(f"[llm-judge] {server.name}: [{i + 1}/{total}] {name} — FAILED: {e}", flush=True)
                result = None
            finally:
                scanner_logger.removeHandler(capture)

            if result is None and cancel_event is not None and cancel_event.is_set():
                print(f"[llm-judge] {server.name}: stopped mid-scan at [{i + 1}/{total}] {name}", flush=True)
                break

            status_error = _status_error_from_logs(capture.messages)
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
    from tooldex.core.discovery.to_manifest import _SEVERITY_RANK

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

        merged = [f for f in server.security_findings if f.get("analyzer") != "LLM"] + llm_findings
        worst = min(
            (f["severity"] for f in merged),
            key=lambda s: _SEVERITY_RANK.get(s.upper(), 99),
            default=None,
        )
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
