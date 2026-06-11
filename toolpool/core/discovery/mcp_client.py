"""
toolpool/core/discovery/mcp_client.py

Async MCP client — connects to a stdio MCP server, calls tools/list,
returns a ToolDiscoveryResult.

Phase 1 scope: stdio transport only. SSE and streamable-http will land
alongside remote-server autodiscovery in Phase 2.

Design notes
------------
- One probe == one short-lived subprocess. We spawn the MCP server,
  complete the initialize handshake, call tools/list, then tear down.
- Env is merged with os.environ so PATH / HOME etc. survive. Server-
  specific env vars from the config override the parent env.
- Hard timeout wraps the entire probe including cleanup. A broken MCP
  server that hangs on shutdown must never block toolpool.
- All exceptions become ToolDiscoveryResult entries — we never raise to
  the caller. Discovery's job is to report; the caller decides what's
  an error worth surfacing.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Optional

from toolpool.core.discovery.results import (
    DiscoveredTool,
    ToolDiscoveryResult,
    ToolDiscoveryStatus,
)
from toolpool.core.models.server import MCPServer

logger = logging.getLogger("toolpool.discovery.mcp_client")


DEFAULT_TIMEOUT_SECONDS = 10.0


async def probe_server(
    server: MCPServer,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> ToolDiscoveryResult:
    """
    Connect to one stdio MCP server and list its tools.

    Never raises — every failure mode becomes a ToolDiscoveryResult with a
    descriptive status and error string. This keeps callers free of
    try/except boilerplate and makes the CLI summary uniform.
    """
    # -- validate transport early ---------------------------------------------
    if server.transport and server.transport != "stdio":
        return ToolDiscoveryResult(
            server_id=server.id,
            status=ToolDiscoveryStatus.UNSUPPORTED_TRANSPORT,
            error=(
                f"Transport {server.transport!r} is not supported in this "
                "build. Phase 1 supports stdio only."
            ),
        )

    if not server.command:
        return ToolDiscoveryResult(
            server_id=server.id,
            status=ToolDiscoveryStatus.MISSING_COMMAND,
            error="Stdio server has no `command` field — cannot spawn.",
        )

    # -- defer SDK import so the module loads even without `mcp` installed ---
    # (useful for tests that don't exercise the live path)
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
    except ImportError as exc:
        return ToolDiscoveryResult(
            server_id=server.id,
            status=ToolDiscoveryStatus.CONNECTION_FAILED,
            error=f"MCP SDK not installed: {exc}. Run `pip install mcp`.",
        )

    # Merge server env on top of parent env so PATH etc. survive.
    merged_env = dict(os.environ)
    merged_env.update(server.env or {})

    params = StdioServerParameters(
        command=server.command,
        args=list(server.args or []),
        env=merged_env,
    )

    start = time.monotonic()
    try:
        result = await asyncio.wait_for(
            _run_probe(params, server.id, ClientSession, stdio_client),
            timeout=timeout,
        )
        result.duration_ms = int((time.monotonic() - start) * 1000)
        return result
    except asyncio.TimeoutError:
        return ToolDiscoveryResult(
            server_id=server.id,
            status=ToolDiscoveryStatus.TIMEOUT,
            error=f"Probe exceeded {timeout:.1f}s timeout.",
            duration_ms=int((time.monotonic() - start) * 1000),
        )
    except FileNotFoundError as exc:
        # Most common concrete failure: `npx` / `uvx` / etc not on PATH.
        return ToolDiscoveryResult(
            server_id=server.id,
            status=ToolDiscoveryStatus.CONNECTION_FAILED,
            error=f"Command not found: {exc}",
            duration_ms=int((time.monotonic() - start) * 1000),
        )
    except Exception as exc:  # noqa: BLE001 — discovery must not propagate
        logger.debug("probe_server error for %s", server.id, exc_info=True)
        cause = _root_cause(exc)
        return ToolDiscoveryResult(
            server_id=server.id,
            status=ToolDiscoveryStatus.PROTOCOL_ERROR,
            error=f"{type(cause).__name__}: {cause}",
            duration_ms=int((time.monotonic() - start) * 1000),
        )


def _root_cause(exc: BaseException) -> BaseException:
    """
    Unwrap nested (Base)ExceptionGroups down to the innermost exception.

    anyio task groups (stdio_client, ClientSession) wrap failures in
    ExceptionGroups, often nested several levels deep. The outer message
    — "unhandled errors in a TaskGroup (1 sub-exception)" — carries no
    information about what actually failed (e.g. EADDRINUSE from an
    `mcp-remote` OAuth callback port collision, or "Connection closed").
    Duck-typing on `.exceptions` avoids depending on the `ExceptionGroup`
    builtin, which only exists on Python 3.11+.
    """
    while True:
        sub = getattr(exc, "exceptions", None)
        if not sub:
            return exc
        exc = sub[0]


async def _run_probe(
    params,
    server_id: str,
    ClientSession,
    stdio_client,
) -> ToolDiscoveryResult:
    """
    Inner probe: open transport, initialize, list_tools. Split out so the
    outer `probe_server` can wrap this whole thing in a single timeout.
    """
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            response = await session.list_tools()

    tools = [
        DiscoveredTool(
            name=tool.name,
            server_id=server_id,
            description=tool.description,
            # inputSchema is a pydantic model in newer SDKs — coerce to dict
            input_schema=_to_dict(getattr(tool, "inputSchema", None)),
        )
        for tool in response.tools
    ]

    return ToolDiscoveryResult(
        server_id=server_id,
        status=ToolDiscoveryStatus.FOUND if tools else ToolDiscoveryStatus.EMPTY,
        tools=tools,
    )


def _to_dict(value) -> Optional[dict]:
    """Coerce the MCP SDK's inputSchema (dict or pydantic model) to a plain dict."""
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    # pydantic BaseModel
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        return dump()
    return None


# ---------------------------------------------------------------------------
# Concurrent probe of many servers
# ---------------------------------------------------------------------------

DEFAULT_CONCURRENCY = 8


async def probe_all(
    servers: list[MCPServer],
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    concurrency: int = DEFAULT_CONCURRENCY,
) -> list[ToolDiscoveryResult]:
    """
    Probe many servers concurrently, bounded by `concurrency`.

    Order of returned results matches order of input servers. Each server's
    outcome is independent — one failure never stops the others.
    """
    if not servers:
        return []

    sem = asyncio.Semaphore(concurrency)

    async def _guarded(server: MCPServer) -> ToolDiscoveryResult:
        async with sem:
            return await probe_server(server, timeout=timeout)

    return await asyncio.gather(*[_guarded(s) for s in servers])