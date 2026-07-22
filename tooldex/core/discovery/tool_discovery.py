"""
tooldex/core/discovery/tool_discovery.py

Sync wrappers around the async MCP client. The rest of tooldex (CLI,
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

from tooldex.core.discovery.mcp_client import (
    DEFAULT_CONCURRENCY,
    DEFAULT_HTTP_CONCURRENCY,
    DEFAULT_TIMEOUT_SECONDS,
    probe_all,
    probe_server,
)
from tooldex.core.discovery.results import DiscoveredTool, ToolDiscoveryResult, ToolDiscoveryStatus
from tooldex.core.models.server import MCPServer

logger = logging.getLogger("tooldex.discovery.tools")


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
    http_concurrency: int = DEFAULT_HTTP_CONCURRENCY,
    use_cache: bool = True,
    cache_ttl: float = 300.0,
) -> list[ToolDiscoveryResult]:
    """
    Sync wrapper: probe many servers concurrently. Returns results in the
    same order as the input list.

    Cache behaviour (use_cache=True by default):
    - Results are cached in ~/.tooldex/probe_cache.json for `cache_ttl` seconds.
    - Only servers whose config changed since the last probe are re-probed live.
    - Pass use_cache=False to force a live probe of every server (explicit rescan).

    Servers with discovered_tools already populated (e.g. from Docker MCP
    Toolkit profile snapshots) are never re-probed — a synthetic FOUND result is
    returned so the CLI summary and API responses stay uniform.
    """
    to_probe   = [s for s in servers if not s.discovered_tools]
    pre_loaded = [s for s in servers if s.discovered_tools]

    cached_results: dict[str, ToolDiscoveryResult] = {}
    still_to_probe: list[MCPServer] = []

    if use_cache:
        from tooldex.core.discovery.probe_cache import get_cached, put_cached as _put
        for s in to_probe:
            hit = get_cached(s, ttl=cache_ttl)
            if hit is not None:
                cached_results[s.id] = hit
                logger.debug("cache hit: %s (%d tools)", s.id, len(hit.tools))
            else:
                still_to_probe.append(s)
    else:
        still_to_probe = to_probe

    probe_results = (
        _run(probe_all(
            still_to_probe,
            timeout=timeout,
            concurrency=concurrency,
            http_concurrency=http_concurrency,
        ))
        if still_to_probe else []
    )

    # Persist new results to cache
    if use_cache:
        from tooldex.core.discovery.probe_cache import put_cached
        server_by_id = {s.id: s for s in still_to_probe}
        for r in probe_results:
            if s := server_by_id.get(r.server_id):
                put_cached(s, r)

    synthetic = [
        ToolDiscoveryResult(
            server_id=s.id,
            status=ToolDiscoveryStatus.FOUND,
            tools=[
                DiscoveredTool(name=t.name, server_id=s.id, description=t.description)
                for t in s.discovered_tools
            ],
        )
        for s in pre_loaded
    ]

    # Restore the original input order so callers can zip servers ↔ results.
    order = {s.id: i for i, s in enumerate(servers)}
    all_results = list(cached_results.values()) + probe_results + synthetic
    all_results.sort(key=lambda r: order.get(r.server_id, len(servers)))
    return all_results


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