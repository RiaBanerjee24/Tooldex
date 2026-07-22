"""
tooldex/scanner/__init__.py

Security scanning integration using the Cisco AI Defense MCP Scanner.

Free analyzers (YARA, Prompt Defense, Readiness) run automatically on every
`tooldex run` with no configuration needed.

Opt-in analyzers activate when the relevant env vars are present:
  MCP_SCANNER_LLM_API_KEY            — enables LLM-as-judge + behavioral analysis
  MCP_SCANNER_LLM_MODEL              — model to use (e.g. gpt-4o, claude-3-5-sonnet)
  MCP_SCANNER_LLM_RATE_LIMIT_DELAY   — seconds between LLM calls (default: 2.0)
  MCP_SCANNER_CONCURRENCY            — max servers scanned in parallel (default: 3)
  MCP_SCANNER_API_KEY                — enables Cisco AI Defense cloud analysis
  VIRUSTOTAL_API_KEY                 — enables VirusTotal binary/package scanning
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
    AnalyzerEnum.PROMPT_DEFENSE,
    AnalyzerEnum.READINESS,
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
    ):
        logging.getLogger(name).setLevel(logging.WARNING)


_silence_llm_loggers()


def _build_config() -> Config:
    rate_limit_delay = float(os.getenv("MCP_SCANNER_LLM_RATE_LIMIT_DELAY", "2.0"))
    return Config(
        api_key=os.getenv("MCP_SCANNER_API_KEY"),
        llm_provider_api_key=os.getenv("MCP_SCANNER_LLM_API_KEY"),
        llm_model=os.getenv("MCP_SCANNER_LLM_MODEL"),
        llm_rate_limit_delay=rate_limit_delay,
        virustotal_api_key=os.getenv("VIRUSTOTAL_API_KEY"),
    )


def active_analyzers(config: Config | None = None) -> list[AnalyzerEnum]:
    if config is None:
        config = _build_config()
    analyzers = list(_FREE_ANALYZERS)
    if config.llm_provider_api_key:
        analyzers += [AnalyzerEnum.LLM, AnalyzerEnum.BEHAVIORAL]
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

    # Limit concurrent server scans to avoid hammering the LLM API.
    # mcpscanner scans all tools within a server in parallel, so concurrency=3
    # with 20 tools/server = 60 simultaneous LLM calls. Default to 1 (sequential)
    # when LLM is active; raise via MCP_SCANNER_CONCURRENCY if you have headroom.
    has_llm = bool(config.llm_provider_api_key)
    default_concurrency = "1" if has_llm else "8"
    concurrency = int(os.getenv("MCP_SCANNER_CONCURRENCY", default_concurrency))
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
