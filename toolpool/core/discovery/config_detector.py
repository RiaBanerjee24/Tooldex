"""
toolpool/core/discovery/config_detector.py

Public entry point for MCP config-file autodiscovery.

Reads known MCP-client config files, parses each into MCPServer instances,
and returns a deduplicated ConfigDetectionResult.

Path resolution lives in _paths.py.
Env resolution and shape parsing live in _parsers.py.
"""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Optional

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

from toolpool.core.discovery._parsers import parse_claude_json, parse_mcp_servers
from toolpool.core.discovery._paths import (
    CLIENT_PRIORITY,
    build_plan,
    claude_code_user_path,
    codex_project_path,
    codex_user_path,
)
from toolpool.core.discovery._docker_mcp import read_all_docker_mcp_profiles
from toolpool.core.discovery.results import (
    ConfigDetectionResult,
    DiscoverySource,
    SourceStatus,
)

logger = logging.getLogger("toolpool.discovery.config")


# ---------------------------------------------------------------------------
# Per-client file readers
# ---------------------------------------------------------------------------

def _read_one(
    client: str,
    path: Optional[Path],
    env: Optional[dict[str, str]] = None,
) -> Optional[DiscoverySource]:
    """
    Read one JSON config file and return a DiscoverySource.

    Returns None when `path` is None (path resolution came up empty —
    e.g. no .cursor/mcp.json anywhere up the tree). That lets the caller
    skip recording sources that were never applicable.
    """
    if path is None:
        return None

    path_str = str(path)

    if not path.exists():
        return DiscoverySource(client=client, path=path_str, status=SourceStatus.NOT_FOUND)

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return DiscoverySource(client=client, path=path_str, status=SourceStatus.READ_ERROR, error=str(exc))

    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        return DiscoverySource(
            client=client, path=path_str, status=SourceStatus.PARSE_ERROR,
            error=f"Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}",
        )

    if not isinstance(raw, dict):
        return DiscoverySource(
            client=client, path=path_str, status=SourceStatus.PARSE_ERROR,
            error=f"Top-level JSON must be an object, got {type(raw).__name__}",
        )

    servers = parse_mcp_servers(raw, path_str, env=env)
    status = SourceStatus.FOUND if servers else SourceStatus.EMPTY
    return DiscoverySource(client=client, path=path_str, status=status, servers=servers)


def _read_claude_json(
    cwd: Path,
    env: Optional[dict[str, str]] = None,
) -> Optional[DiscoverySource]:
    """Read ~/.claude.json and extract both user-level and project-level mcpServers."""
    path = claude_code_user_path()
    path_str = str(path)
    client = "claude_code_user"

    if not path.exists():
        return DiscoverySource(client=client, path=path_str, status=SourceStatus.NOT_FOUND)

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return DiscoverySource(client=client, path=path_str, status=SourceStatus.READ_ERROR, error=str(exc))

    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        return DiscoverySource(
            client=client, path=path_str, status=SourceStatus.PARSE_ERROR,
            error=f"Invalid JSON at line {exc.lineno}: {exc.msg}",
        )

    if not isinstance(raw, dict):
        return DiscoverySource(
            client=client, path=path_str, status=SourceStatus.PARSE_ERROR,
            error=f"Expected object, got {type(raw).__name__}",
        )

    servers = parse_claude_json(raw, path_str, cwd, env=env)
    status = SourceStatus.FOUND if servers else SourceStatus.EMPTY
    return DiscoverySource(client=client, path=path_str, status=status, servers=servers)


def _read_codex_toml(
    path: Path,
    client: str,
    env: Optional[dict[str, str]] = None,
) -> DiscoverySource:
    """Read a Codex TOML config and extract `[mcp_servers.<id>]` tables."""
    path_str = str(path)

    if not path.exists():
        return DiscoverySource(client=client, path=path_str, status=SourceStatus.NOT_FOUND)

    try:
        data = path.read_bytes()
    except OSError as exc:
        return DiscoverySource(client=client, path=path_str, status=SourceStatus.READ_ERROR, error=str(exc))

    try:
        raw = tomllib.loads(data.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        return DiscoverySource(
            client=client, path=path_str, status=SourceStatus.PARSE_ERROR,
            error=f"Invalid TOML: {exc}",
        )

    if not isinstance(raw, dict):
        return DiscoverySource(
            client=client, path=path_str, status=SourceStatus.PARSE_ERROR,
            error=f"Top-level TOML must be a table, got {type(raw).__name__}",
        )

    servers = parse_mcp_servers(raw, path_str, env=env, key="mcp_servers")
    status = SourceStatus.FOUND if servers else SourceStatus.EMPTY
    return DiscoverySource(client=client, path=path_str, status=status, servers=servers)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def detect_all(
    cwd: Optional[Path] = None,
    env: Optional[dict[str, str]] = None,
    custom_paths: Optional[list[Path]] = None,
    auto_detect: bool = True,
    allow_claude_status: bool = True,
    allow_codex_status: bool = True,
    allow_cursor_status: bool = True,
) -> ConfigDetectionResult:
    """
    Check config locations and return an aggregate of discovered servers.

    Parameters
    ----------
    cwd : Path, optional
        Directory from which to search for project-local configs. Defaults
        to Path.cwd(). Has no effect when `auto_detect=False`.
    env : dict, optional
        Environment for resolving ${VAR} references. Defaults to os.environ.
    custom_paths : list[Path], optional
        Explicit paths to MCP config files. Processed BEFORE built-in
        locations so user-specified configs win on duplicate server IDs.
        A path that does not exist or can't be parsed is recorded as a
        failed DiscoverySource rather than aborting the rest.
    auto_detect : bool
        When False, skip all built-in client locations and only read
        `custom_paths`. Useful for hermetic tests and CI runs.
    """
    cwd = cwd or Path.cwd()
    result = ConfigDetectionResult()

    # ── 1. Custom paths — processed first so they win on duplicate IDs ────────
    for raw_path in (custom_paths or []):
        path = Path(raw_path).expanduser().resolve()
        source = _read_one("custom", path, env=env)
        assert source is not None
        result.sources.append(source)
        _merge_servers(result, source, client="custom")

    if not auto_detect:
        return result

    # ── 2. Claude Code global (~/.claude.json) ────────────────────────────────
    source = _read_claude_json(cwd, env=env)
    if source is not None:
        result.sources.append(source)
        _merge_servers(result, source, client="claude_code_user")

    # ── 3. Codex project (<project>/.codex/config.toml) ──────────────────────
    project_codex = codex_project_path(cwd)
    if project_codex is not None:
        source = _read_codex_toml(project_codex, client="codex_project", env=env)
        result.sources.append(source)
        _merge_servers(result, source, client="codex_project")

    # ── 4. Codex global (~/.codex/config.toml) ───────────────────────────────
    source = _read_codex_toml(codex_user_path(), client="codex", env=env)
    result.sources.append(source)
    _merge_servers(result, source, client="codex")

    # ── 5. JSON-based clients (Claude Desktop, Claude Code project, Cursor, Windsurf)
    # walk_up_for() stops at home so project paths can never resolve to global files.
    priority_index = {c: i for i, c in enumerate(CLIENT_PRIORITY)}
    plan = sorted(build_plan(cwd), key=lambda item: priority_index.get(item[0], 999))

    for client, resolver in plan:
        try:
            path = resolver()
        except Exception as exc:
            logger.warning("Path resolution failed for %s: %s", client, exc)
            continue

        source = _read_one(client, path, env=env)
        if source is None:
            continue

        result.sources.append(source)
        _merge_servers(result, source, client=client)

    # ── 6. Docker MCP Toolkit profiles ───────────────────────────────────────
    for source in read_all_docker_mcp_profiles():
        result.sources.append(source)
        _merge_servers(result, source, client=source.client)

    # ── 7. Enrich Claude-sourced servers via `claude mcp list` ───────────────
    if allow_claude_status:
        claude_statuses = _fetch_claude_status()
        for qid, server in result.servers.items():
            if server.client and server.client.startswith("claude_code"):
                status = claude_statuses.get(server.name)
                if status:
                    result.servers[qid] = server.model_copy(
                        update={"connection_status": status, "raw_connection_status": status}
                    )

    # ── 8. Enrich Codex-sourced servers via `codex mcp list` ─────────────────
    if allow_codex_status:
        codex_statuses = _fetch_codex_status()
        for qid, server in result.servers.items():
            if server.client and server.client.startswith("codex"):
                status = codex_statuses.get(server.name)
                if status:
                    result.servers[qid] = server.model_copy(
                        update={"connection_status": status, "raw_connection_status": status}
                    )

    # ── 9. Enrich Cursor-sourced servers via `cursor-agent mcp list` ──────────
    if allow_cursor_status:
        cursor_statuses = _fetch_cursor_status()
        for qid, server in result.servers.items():
            if server.client and server.client.startswith("cursor"):
                entry = cursor_statuses.get(server.name)
                if entry:
                    status, raw = entry
                    result.servers[qid] = server.model_copy(
                        update={"connection_status": status, "raw_connection_status": raw}
                    )

    return result


# ---------------------------------------------------------------------------
# Claude live-status enrichment
# ---------------------------------------------------------------------------

def _fetch_claude_status() -> dict[str, str]:
    """
    Run `claude mcp list` and return {server_name: status}.

    Output format (one server per line):
        name: command/url - ✔ Connected
        name: command/url - ✘ Failed to connect
        name: command/url - ! Needs authentication

    Returns an empty dict if `claude` is not on PATH or the command times out.
    """
    try:
        proc = subprocess.run(
            ["claude", "mcp", "list"],
            capture_output=True, text=True, timeout=15,
        )
        output = proc.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return {}

    statuses: dict[str, str] = {}
    for line in output.splitlines():
        line = line.strip()
        if not line or " - " not in line:
            continue
        name_cmd, _, status_raw = line.rpartition(" - ")
        name = name_cmd.split(": ", 1)[0].strip()
        if not name:
            continue
        s = status_raw.strip()
        if s.startswith("✔"):
            statuses[name] = "connected"
        elif s.startswith("✘"):
            statuses[name] = "failed"
        elif s.startswith("!"):
            statuses[name] = "needs_auth"

    return statuses


def _fetch_cursor_status() -> dict[str, tuple[str, str]]:
    """
    Run `cursor-agent mcp list` and return {server_name: (status, raw_string)}.

    Output format:
        browserbase: not loaded (needs approval)
        filesystem: running

    Status mapping:
        contains "running" or "connected" → "connected"
        contains "needs approval"         → "needs_auth"
        anything else                     → "failed"
    """
    try:
        proc = subprocess.run(
            ["cursor-agent", "mcp", "list"],
            capture_output=True, text=True, timeout=15,
        )
        output = proc.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return {}

    result: dict[str, tuple[str, str]] = {}
    for line in output.splitlines():
        line = line.strip()
        if not line or ": " not in line:
            continue
        name, _, raw = line.partition(": ")
        name = name.strip()
        raw = raw.strip()
        if not name or not raw:
            continue
        low = raw.lower()
        if "running" in low or "connected" in low:
            status = "connected"
        elif "needs approval" in low or "needs_auth" in low:
            status = "needs_auth"
        else:
            status = "failed"
        result[name] = (status, raw)
    return result


def _fetch_codex_status() -> dict[str, str]:
    """
    Run `codex mcp list` and return {server_name: status}.

    Output is a fixed-width table with two sections (stdio + HTTP), each
    with its own header row. The Status column position is read from each
    header so column shifts between sections are handled correctly.

        Name        Command  Args  ...  Status   Auth
        MCP_DOCKER  docker   ...        enabled  Unsupported

    "enabled" → "connected"; anything else → "failed".
    """
    try:
        proc = subprocess.run(
            ["codex", "mcp", "list"],
            capture_output=True, text=True, timeout=15,
        )
        output = proc.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return {}

    statuses: dict[str, str] = {}
    status_col: int | None = None

    for line in output.splitlines():
        if not line.strip():
            status_col = None  # blank line separates table sections — reset
            continue

        if "Name" in line and "Status" in line:
            status_col = line.index("Status")
            continue

        if status_col is None:
            continue

        parts = line.split()
        if not parts:
            continue
        name = parts[0]

        if len(line) > status_col:
            after = line[status_col:].split()
            if after:
                raw = after[0].lower()
                statuses[name] = "connected" if raw == "enabled" else "failed"

    return statuses


# ---------------------------------------------------------------------------
# Merge helpers
# ---------------------------------------------------------------------------

def _merge_servers(
    result: ConfigDetectionResult,
    source: DiscoverySource,
    client: str,
) -> None:
    """
    Add a source's servers into result, keyed by "{client}:{server_id}".

    Dedup rules:
    - Same (client, server_id): first-sighting wins. Within a single client
      source, global-scope entries are yielded before project-scope entries
      (see parse_claude_json), so global naturally takes precedence.
    - Different clients with the same server name are independent entries —
      claude_code_user:filesystem and cursor_user:filesystem are both kept.
    """
    for server in source.servers:
        qualified_id = f"{client}:{server.id}"
        if qualified_id not in result.servers:
            result.servers[qualified_id] = server.model_copy(
                update={"client": client, "id": qualified_id}
            )
