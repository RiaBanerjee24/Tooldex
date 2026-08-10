"""tooldex/scanner/yara_scan.py — automatic, always-on fleet-wide YARA scan."""
from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING

from mcpscanner import Scanner
from mcpscanner.core.models import AnalyzerEnum
from mcpscanner.core.result import ToolScanResult
from mcpscanner.core.scanner import StdioServer

from tooldex._env_bool import env_flag_enabled
from tooldex.scanner.config import build_config

if TYPE_CHECKING:
    from tooldex.core.models.server import MCPServer

_FREE_ANALYZERS = [
    AnalyzerEnum.YARA,
]


def active_analyzers() -> list[AnalyzerEnum]:
    """Analyzers used by the automatic fleet-wide scan (scan_servers)."""
    return list(_FREE_ANALYZERS)


def security_scan_enabled() -> bool:
    """
    Single source of truth for whether the automatic YARA scan should run at
    all. TOOLDEX_SECURITY_SCAN=false disables it — checked both at startup
    (cli.py) and on every rescan (api/routers/rescan.py). The --no-security-scan
    CLI flag works by setting this env var for the process, so both call
    sites stay in sync without duplicating the enable/disable logic.
    """
    return env_flag_enabled("TOOLDEX_SECURITY_SCAN", default=True)


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
    config = build_config()
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
