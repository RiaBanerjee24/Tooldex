"""
tooldex/scanner/__init__.py

Security scanning integration using the Cisco AI Defense MCP Scanner.

The free analyzer (YARA) runs automatically on every `tooldex run` with no
configuration needed. It pattern-matches actual attack payloads (instruction
overrides, hidden-instruction evasion, privilege escalation strings) in tool
descriptions and output, so a finding means suspicious content is actually
present.

Prompt Defense and Readiness are excluded from the default set: both flag
the *absence* of specific boilerplate wording rather than the presence of
any actual issue, so they produce a HIGH/MEDIUM on nearly every real-world
tool regardless of risk and aren't actionable for servers you don't control.

Opt-in analyzers activate when the relevant env vars are present:
  MCP_SCANNER_API_KEY                — enables Cisco AI Defense cloud analysis
  VIRUSTOTAL_API_KEY                 — enables VirusTotal binary/package scanning
  MCP_SCANNER_CONCURRENCY            — max servers scanned in parallel (default: 8)

LLM-as-judge is opt-in and per-server only — it does NOT run automatically
on `tooldex run` or a fleet-wide rescan, even when MCP_SCANNER_LLM_API_KEY is
set. mcpscanner's bulk scan fires every tool on a server through the LLM
concurrently with no cap, so running it automatically across an entire
fleet (potentially hundreds of tools) reliably bursts through provider rate
limits and stalls for a long time retrying silently. Setting the LLM env
vars only unlocks the "run llm judge" button per server (see
scan_server_llm_judge below), which scans that server's tools one at a time:
  MCP_SCANNER_LLM_API_KEY            — enables the per-server LLM judge button
  MCP_SCANNER_LLM_MODEL              — model to use (e.g. gpt-4o, claude-3-5-sonnet)
  MCP_SCANNER_LLM_RATE_LIMIT_DELAY   — seconds between LLM calls (default: 2.0)
  MCP_SCANNER_LLM_TEMPERATURE        — sampling temperature (default: 1.0 — mcpscanner
                                        defaults to 0.1, which reasoning-tier models like
                                        gpt-5.6-terra/sol reject outright with a 400;
                                        1.0 is accepted by both classic and reasoning models)
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import TYPE_CHECKING

from mcpscanner import Config, Scanner
from mcpscanner.core.models import AnalyzerEnum, ToolScanResult
from mcpscanner.core.scanner import StdioServer

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
    rate_limit_delay = float(os.getenv("MCP_SCANNER_LLM_RATE_LIMIT_DELAY", "2.0"))
    max_retries = int(os.getenv("MCP_SCANNER_LLM_MAX_RETRIES", "6"))
    temperature = float(os.getenv("MCP_SCANNER_LLM_TEMPERATURE", "1.0"))
    return Config(
        api_key=os.getenv("MCP_SCANNER_API_KEY"),
        llm_provider_api_key=os.getenv("MCP_SCANNER_LLM_API_KEY"),
        llm_model=os.getenv("MCP_SCANNER_LLM_MODEL"),
        llm_rate_limit_delay=rate_limit_delay,
        llm_max_retries=max_retries,
        llm_temperature=temperature,
        virustotal_api_key=os.getenv("VIRUSTOTAL_API_KEY"),
    )


def active_analyzers(config: Config | None = None) -> list[AnalyzerEnum]:
    """
    Analyzers used by the automatic fleet-wide scan (scan_servers). Deliberately
    excludes LLM/BEHAVIORAL regardless of whether an LLM key is configured —
    see the module docstring for why. Those only run via scan_server_llm_judge.
    """
    if config is None:
        config = _build_config()
    analyzers = list(_FREE_ANALYZERS)
    if config.api_key:
        analyzers.append(AnalyzerEnum.API)
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

    # No LLM analyzer in this path (see active_analyzers), so there's no
    # provider rate limit to protect — just cap parallel server scans.
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
    """
    Run the security scan on a set of already-probed servers.
    Returns server_id → list of per-tool scan results.
    """
    if not servers:
        return {}
    return asyncio.run(_scan_all_async(servers))


async def _scan_llm_judge_async(server: MCPServer) -> list[ToolScanResult]:
    config = _build_config()
    if not config.llm_provider_api_key:
        raise ValueError("MCP_SCANNER_LLM_API_KEY is not configured")

    scanner = Scanner(config)
    delay = config.llm_rate_limit_delay
    tool_names = [t.name for t in server.discovered_tools]
    if not tool_names:
        return []

    results: list[ToolScanResult] = []
    total = len(tool_names)
    print(f"[llm-judge] {server.name}: scanning {total} tool(s), ~{delay:.0f}s+ apart", flush=True)
    devnull = open(os.devnull, "w")
    try:
        for i, name in enumerate(tool_names):
            if i > 0:
                await asyncio.sleep(delay)
            print(f"[llm-judge] {server.name}: [{i + 1}/{total}] {name} …", flush=True)
            try:
                if server.transport == "stdio" and server.command:
                    env = {**os.environ, **(server.env or {})}
                    stdio_cfg = StdioServer(
                        command=server.command,
                        args=server.args or [],
                        env=env,
                    )
                    result = await scanner.scan_stdio_server_tool(
                        stdio_cfg, name, analyzers=[AnalyzerEnum.LLM], errlog=devnull
                    )
                elif server.url:
                    result = await scanner.scan_remote_server_tool(
                        server.url, name, analyzers=[AnalyzerEnum.LLM]
                    )
                else:
                    print(f"[llm-judge] {server.name}: [{i + 1}/{total}] {name} — skipped (no command/url)", flush=True)
                    continue
            except Exception as e:
                print(f"[llm-judge] {server.name}: [{i + 1}/{total}] {name} — FAILED: {e}", flush=True)
                continue
            results.append(result)
    finally:
        devnull.close()

    print(f"[llm-judge] {server.name}: done — {len(results)}/{total} tools scanned", flush=True)
    return results


def scan_server_llm_judge(server: MCPServer) -> list[ToolScanResult]:
    """
    Run the LLM-as-judge analyzer over one server's tools, one tool at a time.

    mcpscanner's bulk scan (scan_stdio_server_tools / scan_remote_server_tools)
    fires every tool on a server through the LLM concurrently with no cap —
    a 20-tool server means 20 simultaneous LLM calls, which is what trips
    provider rate limits. Scanning tool-by-tool with a delay between calls
    guarantees at most one in-flight LLM request at a time.
    """
    return asyncio.run(_scan_llm_judge_async(server))
