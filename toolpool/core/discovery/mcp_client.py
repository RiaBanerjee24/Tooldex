"""
toolpool/core/discovery/mcp_client.py

Async MCP client — connects to an MCP server, calls tools/list, and returns
a ToolDiscoveryResult. Supports stdio, HTTP (streamable-http), and SSE.

For Cursor-sourced HTTP/SSE servers that reject the native probe (e.g. due to
missing auth), we automatically fall back to `cursor-agent mcp list-tools`
which uses Cursor's own credentials/session.

Design notes
------------
- One probe == one short-lived connection. We connect, initialize, call
  tools/list, then tear down.
- Env is merged with os.environ so PATH / HOME etc. survive for stdio.
- Hard timeout wraps the entire probe including cleanup.
- All exceptions become ToolDiscoveryResult entries — we never raise to
  the caller.
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

# Maps client-name prefix → CLI command prefix for listing tools.
# Format: the server name is appended as the final argument.
# Add entries here as we confirm each client's CLI supports tool listing.
_AGENT_FALLBACK_CMDS: dict[str, list[str]] = {
    "cursor": ["cursor-agent", "mcp", "list-tools"],
    # "claude_code": ["claude", "mcp", "list-tools"],   # confirm command first
    # "codex":       ["codex",  "mcp", "list-tools"],   # confirm command first
}


def _fallback_cmd(client: str | None) -> list[str] | None:
    """Return the CLI command list for this client, or None if unsupported."""
    if not client:
        return None
    for prefix, cmd in _AGENT_FALLBACK_CMDS.items():
        if client.startswith(prefix):
            return cmd
    return None


async def probe_server(
    server: MCPServer,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> ToolDiscoveryResult:
    """
    Connect to one MCP server and list its tools.

    Routes by server.transport ("stdio" | "http" | "sse"). For Cursor-sourced
    HTTP/SSE servers, falls back to cursor-agent if the native probe fails.
    Never raises.
    """
    transport = (server.transport or "stdio").lower()

    if transport == "stdio":
        return await _probe_with_timeout(_probe_stdio, server, timeout)

    if transport in ("http", "sse"):
        probe_fn = _probe_http if transport == "http" else _probe_sse
        result = await _probe_with_timeout(probe_fn, server, timeout)
        if not result.ok and _fallback_cmd(server.client):
            fallback = await _probe_via_agent(server)
            if fallback.ok:
                return fallback
        return result

    return ToolDiscoveryResult(
        server_id=server.id,
        status=ToolDiscoveryStatus.UNSUPPORTED_TRANSPORT,
        error=f"Transport {server.transport!r} is not supported.",
    )


# ---------------------------------------------------------------------------
# Shared timeout wrapper
# ---------------------------------------------------------------------------

async def _probe_with_timeout(probe_fn, server: MCPServer, timeout: float) -> ToolDiscoveryResult:
    start = time.monotonic()
    try:
        result = await asyncio.wait_for(probe_fn(server), timeout=timeout)
        result.duration_ms = int((time.monotonic() - start) * 1000)
        return result
    except asyncio.TimeoutError:
        return ToolDiscoveryResult(
            server_id=server.id,
            status=ToolDiscoveryStatus.TIMEOUT,
            error=f"Probe exceeded {timeout:.1f}s timeout.",
            duration_ms=int((time.monotonic() - start) * 1000),
        )
    except FileNotFoundError:
        cmd = server.command or ""
        hint = _RUNTIME_HINTS.get(cmd)
        error = f"'{cmd}' is not installed" + (f" — {hint}" if hint else "")
        return ToolDiscoveryResult(
            server_id=server.id,
            status=ToolDiscoveryStatus.CONNECTION_FAILED,
            error=error,
            duration_ms=int((time.monotonic() - start) * 1000),
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("probe error for %s", server.id, exc_info=True)
        cause = _root_cause(exc)
        return ToolDiscoveryResult(
            server_id=server.id,
            status=ToolDiscoveryStatus.PROTOCOL_ERROR,
            error=f"{type(cause).__name__}: {cause}",
            duration_ms=int((time.monotonic() - start) * 1000),
        )


# ---------------------------------------------------------------------------
# Stdio probe
# ---------------------------------------------------------------------------

async def _probe_stdio(server: MCPServer) -> ToolDiscoveryResult:
    if not server.command:
        return ToolDiscoveryResult(
            server_id=server.id,
            status=ToolDiscoveryStatus.MISSING_COMMAND,
            error="Stdio server has no `command` field — cannot spawn.",
        )

    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
    except ImportError as exc:
        return ToolDiscoveryResult(
            server_id=server.id,
            status=ToolDiscoveryStatus.CONNECTION_FAILED,
            error=f"MCP SDK not installed: {exc}. Run `pip install mcp`.",
        )

    merged_env = dict(os.environ)
    merged_env.update(server.env or {})

    params = StdioServerParameters(
        command=server.command,
        args=list(server.args or []),
        env=merged_env,
    )

    async with stdio_client(params) as (read, write):
        return await _run_session(read, write, server.id)


# ---------------------------------------------------------------------------
# HTTP (streamable-http) probe
# ---------------------------------------------------------------------------

async def _probe_http(server: MCPServer) -> ToolDiscoveryResult:
    if not server.url:
        return ToolDiscoveryResult(
            server_id=server.id,
            status=ToolDiscoveryStatus.CONNECTION_FAILED,
            error="HTTP server has no `url` field.",
        )

    try:
        from mcp.client.streamable_http import streamable_http_client
    except ImportError as exc:
        return ToolDiscoveryResult(
            server_id=server.id,
            status=ToolDiscoveryStatus.CONNECTION_FAILED,
            error=f"MCP SDK not installed or too old for HTTP: {exc}. Run `pip install mcp`.",
        )

    import httpx
    if server.headers:
        async with httpx.AsyncClient(headers=server.headers) as http_client:
            async with streamable_http_client(server.url, http_client=http_client) as (read, write, _):
                return await _run_session(read, write, server.id)
    else:
        async with streamable_http_client(server.url) as (read, write, _):
            return await _run_session(read, write, server.id)


# ---------------------------------------------------------------------------
# SSE probe
# ---------------------------------------------------------------------------

async def _probe_sse(server: MCPServer) -> ToolDiscoveryResult:
    if not server.url:
        return ToolDiscoveryResult(
            server_id=server.id,
            status=ToolDiscoveryStatus.CONNECTION_FAILED,
            error="SSE server has no `url` field.",
        )

    try:
        from mcp.client.sse import sse_client
    except ImportError as exc:
        return ToolDiscoveryResult(
            server_id=server.id,
            status=ToolDiscoveryStatus.CONNECTION_FAILED,
            error=f"MCP SDK not installed: {exc}. Run `pip install mcp`.",
        )

    headers = server.headers or None
    async with sse_client(server.url, headers=headers) as (read, write):
        return await _run_session(read, write, server.id)


# ---------------------------------------------------------------------------
# cursor-agent fallback (for Cursor-managed HTTP/SSE servers)
# ---------------------------------------------------------------------------

async def _probe_via_agent(server: MCPServer) -> ToolDiscoveryResult:
    """
    Shell out to the client's CLI tool-listing command as a fallback when the
    native probe fails (e.g. due to missing auth). The client maintains its own
    credentials/session so it can reach auth-protected servers.

    Which CLI to call is determined by _fallback_cmd() / _AGENT_FALLBACK_CMDS.
    """
    cmd = _fallback_cmd(server.client)
    if not cmd:
        return ToolDiscoveryResult(
            server_id=server.id,
            status=ToolDiscoveryStatus.UNSUPPORTED_TRANSPORT,
            error=f"No agent fallback registered for client {server.client!r}.",
        )

    full_cmd = cmd + [server.name]  # append unqualified server name
    agent_label = cmd[0]
    try:
        proc = await asyncio.create_subprocess_exec(
            *full_cmd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15.0)
    except FileNotFoundError:
        return ToolDiscoveryResult(
            server_id=server.id,
            status=ToolDiscoveryStatus.CONNECTION_FAILED,
            error=f"{agent_label!r} not found on PATH.",
        )
    except asyncio.TimeoutError:
        return ToolDiscoveryResult(
            server_id=server.id,
            status=ToolDiscoveryStatus.TIMEOUT,
            error=f"{agent_label} timed out.",
        )
    except Exception as exc:  # noqa: BLE001
        return ToolDiscoveryResult(
            server_id=server.id,
            status=ToolDiscoveryStatus.PROTOCOL_ERROR,
            error=f"{agent_label} error: {exc}",
        )

    output = stdout.decode("utf-8", errors="replace")
    tools = _parse_agent_output(output, server.id)

    if not tools:
        return ToolDiscoveryResult(
            server_id=server.id,
            status=ToolDiscoveryStatus.EMPTY,
            error="cursor-agent returned no tools.",
        )

    return ToolDiscoveryResult(
        server_id=server.id,
        status=ToolDiscoveryStatus.FOUND,
        tools=tools,
    )


def _parse_agent_output(output: str, server_id: str) -> list[DiscoveredTool]:
    """
    Parse agent CLI tool-listing output. Expected format (cursor-agent, and
    assumed compatible for other clients as they're added):

        Tools for browserbase (6):
        - act (action)
        - end ()
        - navigate (url)
    """
    tools = []
    for line in output.splitlines():
        line = line.strip()
        if not line.startswith("- "):
            continue
        rest = line[2:]
        if "(" in rest and rest.endswith(")"):
            name = rest[:rest.index("(")].strip()
            params = rest[rest.index("(") + 1:-1].strip()
            description = params if params else None
        else:
            name = rest.strip()
            description = None
        if name:
            tools.append(DiscoveredTool(
                name=name,
                server_id=server_id,
                description=description,
            ))
    return tools


# ---------------------------------------------------------------------------
# Shared session runner
# ---------------------------------------------------------------------------

async def _run_session(read, write, server_id: str) -> ToolDiscoveryResult:
    from mcp import ClientSession

    async with ClientSession(read, write) as session:
        await session.initialize()
        response = await session.list_tools()

    tools = [
        DiscoveredTool(
            name=tool.name,
            server_id=server_id,
            description=tool.description,
            input_schema=_to_dict(getattr(tool, "inputSchema", None)),
        )
        for tool in response.tools
    ]

    return ToolDiscoveryResult(
        server_id=server_id,
        status=ToolDiscoveryStatus.FOUND if tools else ToolDiscoveryStatus.EMPTY,
        tools=tools,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _root_cause(exc: BaseException) -> BaseException:
    """Unwrap nested ExceptionGroups down to the innermost exception."""
    while True:
        sub = getattr(exc, "exceptions", None)
        if not sub:
            return exc
        exc = sub[0]


def _to_dict(value) -> Optional[dict]:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        return dump()
    return None


# ---------------------------------------------------------------------------
# Concurrent probe of many servers
# ---------------------------------------------------------------------------

DEFAULT_CONCURRENCY = 8

_RUNTIME_HINTS: dict[str, str] = {
    "uvx":     "install uv: https://astral.sh/uv",
    "uv":      "install uv: https://astral.sh/uv",
    "npx":     "install Node.js: https://nodejs.org",
    "node":    "install Node.js: https://nodejs.org",
    "npm":     "install Node.js: https://nodejs.org",
    "docker":  "install Docker: https://docs.docker.com/get-docker/",
    "python":  "install Python: https://python.org",
    "python3": "install Python: https://python.org",
    "deno":    "install Deno: https://deno.com",
    "bun":     "install Bun: https://bun.sh",
    "pipx":    "install pipx: https://pipx.pypa.io",
}


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
