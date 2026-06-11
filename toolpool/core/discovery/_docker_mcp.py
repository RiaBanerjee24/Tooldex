"""
toolpool/core/discovery/_docker_mcp.py

Docker MCP Toolkit reader.

`docker mcp profile ls --format json` returns ALL profiles with their full
server and tool snapshots in one call — so we parse everything from that
single output rather than doing a separate `profile show` per profile.

`docker mcp profile show <id> --format json` is used as a per-profile
fallback when the bulk listing isn't available or returns no data.

Tools are embedded in the profile snapshot, so no live MCP probing is
needed for Docker-managed servers.

Private module — imported only by config_detector.py.
"""
from __future__ import annotations

import json
import logging
import subprocess
from typing import Optional

from toolpool.core.discovery.results import DiscoverySource, SourceStatus
from toolpool.core.models.server import DiscoveredToolLite, MCPServer

logger = logging.getLogger("toolpool.discovery.docker_mcp")

_TIMEOUT = 10.0  # seconds per subprocess call


# ---------------------------------------------------------------------------
# Subprocess helper
# ---------------------------------------------------------------------------

def _run(*args: str) -> Optional[str]:
    """
    Run `docker mcp <args>` and return stdout, or None on any failure.

    Never raises — missing docker, docker not running, unknown subcommand, etc.
    all become None so the caller can record a NOT_FOUND source and move on.
    """
    try:
        result = subprocess.run(
            ["docker", "mcp", *args],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
        )
    except FileNotFoundError:
        logger.debug("docker not found on PATH — skipping Docker MCP discovery")
        return None
    except subprocess.TimeoutExpired:
        logger.warning("docker mcp timed out after %.0fs", _TIMEOUT)
        return None
    except OSError as exc:
        logger.debug("docker mcp failed to start: %s", exc)
        return None

    if result.returncode != 0:
        logger.debug(
            "docker mcp %s exited %d: %s",
            " ".join(args), result.returncode, result.stderr.strip(),
        )
        return None

    return result.stdout


# ---------------------------------------------------------------------------
# Profile dict → DiscoverySource
# ---------------------------------------------------------------------------

def _parse_server_entry(entry: dict) -> Optional[MCPServer]:
    """
    Convert one element of a profile's `servers` array into an MCPServer.

    Returns None when the entry is malformed or missing required fields.
    """
    snapshot = entry.get("snapshot") or {}
    srv = snapshot.get("server") or {}

    server_id: Optional[str] = srv.get("name")
    if not server_id:
        return None

    image: str = entry.get("image") or srv.get("image") or ""
    container_args: list[str] = srv.get("command") or []

    # Synthesise a runnable stdio invocation:
    #   docker run -i --rm <image> [container_args…]
    run_args = ["run", "-i", "--rm", image, *container_args] if image else []

    # Tools are embedded in the snapshot — no live probe required.
    tools: list[DiscoveredToolLite] = [
        DiscoveredToolLite(
            name=t["name"],
            description=t.get("description"),
        )
        for t in (srv.get("tools") or [])
        if isinstance(t, dict) and t.get("name")
    ]

    return MCPServer(
        id=server_id,
        name=srv.get("title") or server_id,
        transport="stdio",
        command="docker" if run_args else None,
        args=run_args,
        description=srv.get("description"),
        discovered_tools=tools,
    )


def _source_from_profile_dict(data: dict) -> DiscoverySource:
    """
    Build a DiscoverySource from an already-parsed profile object.

    Used by both the bulk-ls path and the per-profile show path.
    """
    # Profile id is the stable identifier used in CLI commands.
    # Profile name is the human-readable display label.
    profile_id: str = data.get("id") or data.get("name") or "unknown"
    client = f"docker_mcp:{profile_id}"
    path = f"docker mcp profile show {profile_id}"

    servers: list[MCPServer] = []
    for entry in data.get("servers") or []:
        if not isinstance(entry, dict):
            continue
        srv = _parse_server_entry(entry)
        if srv is not None:
            servers.append(srv)
        else:
            logger.warning(
                "Skipping malformed server entry in Docker MCP profile %r",
                profile_id,
            )

    status = SourceStatus.FOUND if servers else SourceStatus.EMPTY
    return DiscoverySource(client=client, path=path, status=status, servers=servers)


# ---------------------------------------------------------------------------
# Per-profile fallback (used when ls --format json is unavailable)
# ---------------------------------------------------------------------------

def _read_profile_by_id(profile_id: str) -> DiscoverySource:
    """
    Read one profile via `docker mcp profile show <id> --format json`.
    """
    client = f"docker_mcp:{profile_id}"
    path = f"docker mcp profile show {profile_id}"

    output = _run("profile", "show", profile_id, "--format", "json")
    if output is None:
        return DiscoverySource(client=client, path=path, status=SourceStatus.NOT_FOUND)

    try:
        data = json.loads(output)
    except json.JSONDecodeError as exc:
        return DiscoverySource(
            client=client, path=path, status=SourceStatus.PARSE_ERROR,
            error=f"Invalid JSON from docker mcp profile show: {exc}",
        )

    if not isinstance(data, dict):
        return DiscoverySource(
            client=client, path=path, status=SourceStatus.PARSE_ERROR,
            error=f"Expected JSON object, got {type(data).__name__}",
        )

    return _source_from_profile_dict(data)


def _profile_ids_from_text() -> list[str]:
    """
    Parse profile IDs from the plain-text output of `docker mcp profile ls`.

    Output format:
        ID        Name
        ----      ----
        toolpool   toolpool
        rochh     rochh
    """
    output = _run("profile", "ls")
    if not output:
        return []

    ids: list[str] = []
    for line in output.strip().splitlines():
        # Skip header and separator lines (contain only dashes or column names)
        stripped = line.strip()
        if not stripped or stripped.startswith("-") or stripped.upper().startswith("ID"):
            continue
        parts = stripped.split()
        if parts:
            ids.append(parts[0])   # first column is the profile ID
    return ids


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def read_all_docker_mcp_profiles() -> list[DiscoverySource]:
    """
    Read every Docker MCP profile on this machine.

    Fast path: `docker mcp profile ls --format json` returns all profiles
    with their full server+tool snapshots in one call.

    Slow path: parse profile IDs from plain-text `docker mcp profile ls`,
    then call `docker mcp profile show <id> --format json` for each.

    Returns an empty list — never an error — when docker or the mcp plugin
    is not installed.
    """
    # ── fast path ─────────────────────────────────────────────────────────────
    output = _run("profile", "ls", "--format", "json")
    if output:
        try:
            data = json.loads(output)
            if isinstance(data, list) and data:
                sources = [
                    _source_from_profile_dict(p)
                    for p in data
                    if isinstance(p, dict)
                ]
                logger.info(
                    "Docker MCP: %d profile(s) loaded from bulk ls",
                    len(sources),
                )
                return sources
        except json.JSONDecodeError:
            pass

    # ── slow path ─────────────────────────────────────────────────────────────
    ids = _profile_ids_from_text()
    if not ids:
        return []

    logger.info("Docker MCP: %d profile(s) found via text ls", len(ids))
    return [_read_profile_by_id(pid) for pid in ids]
