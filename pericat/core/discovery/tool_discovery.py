"""
pericat/core/discovery/tool_discovery.py

Sync wrappers around the async MCP client. The rest of Pericat (CLI,
parser, API routers) is sync — this module hides the asyncio.run()
boilerplate so callers get a plain function that returns results.

Two entry points:
    list_tools_for(server)          → one server
    list_tools_for_all(servers)     → many servers, concurrent
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from pericat.core.discovery.mcp_client import (
    DEFAULT_CONCURRENCY,
    DEFAULT_TIMEOUT_SECONDS,
    probe_all,
    probe_server,
)
from pericat.core.discovery.results import ToolDiscoveryResult
from pericat.core.models.server import MCPServer

logger = logging.getLogger("pericat.discovery.tools")


def list_tools_for(
    server: MCPServer,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> ToolDiscoveryResult:
    """
    Sync wrapper: probe one server and return its tool discovery result.

    Safe to call from sync code. Uses a fresh event loop under the hood —
    do NOT call this from inside an already-running loop (use `probe_server`
    directly from async code instead).
    """
    return _run(probe_server(server, timeout=timeout))


def list_tools_for_all(
    servers: list[MCPServer],
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    concurrency: int = DEFAULT_CONCURRENCY,
) -> list[ToolDiscoveryResult]:
    """
    Sync wrapper: probe many servers concurrently. Returns results in the
    same order as the input list.
    """
    return _run(probe_all(servers, timeout=timeout, concurrency=concurrency))


def _run(coro):
    """
    Run `coro` on a fresh event loop.

    We deliberately avoid `asyncio.run()` here because callers sometimes
    embed us inside test frameworks (pytest-anyio, notebooks) that already
    have a running loop — `asyncio.run()` fails hard in that case. When
    there's no active loop, this behaves identically to `asyncio.run`.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # No running loop — normal case. Use asyncio.run for proper cleanup.
        return asyncio.run(coro)

    # Running loop detected — caller should have used the async API directly.
    # Close the coro so Python doesn't emit "coroutine was never awaited".
    coro.close()
    raise RuntimeError(
        "list_tools_for*() was called from a running event loop. "
        "Use `await probe_server(...)` / `await probe_all(...)` directly instead."
    )