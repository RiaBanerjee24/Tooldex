"""
pericat/core/discovery/config_detector.py

Discovers MCP servers by reading known MCP-client config files.

Supported clients (Phase 1):

    Claude Desktop      claude_desktop_config.json
        macOS    ~/Library/Application Support/Claude/claude_desktop_config.json
        Windows  %APPDATA%\\Claude\\claude_desktop_config.json
        Linux    ~/.config/Claude/claude_desktop_config.json

    Claude Code         .claude/settings.json  (walk up from cwd)
                        ~/.claude/settings.json  (user-level)

    Cursor              ~/.cursor/mcp.json  (user-level)
                        <project>/.cursor/mcp.json  (walk up from cwd)

    Windsurf            ~/.codeium/windsurf/mcp_config.json

All readers share the same MCP server JSON shape popularised by Claude
Desktop:

    {
      "mcpServers": {
        "<server-id>": {
          "command": "npx",           // stdio
          "args": [...],
          "env": {...}
        },
        "<server-id>": {
          "url": "http://...",        // sse / streamable-http
          ...
        }
      }
    }

Anything outside that shape is ignored. Env var references like ${VAR} or
$VAR inside `env` and `args` values are resolved against the shell
environment only — we never read .env files. Unresolved references pass
through as-is so the developer can see them in the UI.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Callable, Optional

from pericat.core.discovery.results import (
    ConfigDetectionResult,
    DiscoverySource,
    SourceStatus,
)
from pericat.core.models import MCPServer

logger = logging.getLogger("pericat.discovery.config")

# Priority order for dedup — first hit wins.
# Rationale: Claude Desktop is the canonical MCP client, Claude Code inherits
# from it, Cursor and Windsurf came later.
_CLIENT_PRIORITY = (
    "claude_desktop",
    "claude_code_project",
    "claude_code_user",
    "cursor_project",
    "cursor_user",
    "windsurf",
)

# ${VAR} or $VAR — standard shell substitution
_ENV_REF = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)")


# ---------------------------------------------------------------------------
# Path resolvers (platform-aware)
# ---------------------------------------------------------------------------

def _claude_desktop_path() -> Path:
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    if sys.platform.startswith("win"):
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else home / "AppData" / "Roaming"
        return base / "Claude" / "claude_desktop_config.json"
    # linux / other
    return home / ".config" / "Claude" / "claude_desktop_config.json"


def _claude_code_user_path() -> Path:
    return Path.home() / ".claude.json"


def _claude_code_project_path(cwd: Path) -> Optional[Path]:
    """Walk up from cwd looking for .claude.json."""
    return _walk_up_for(cwd, (".claude.json"))


def _cursor_user_path() -> Path:
    return Path.home() / ".cursor" / "mcp.json"


def _cursor_project_path(cwd: Path) -> Optional[Path]:
    return _walk_up_for(cwd, (".cursor", "mcp.json"))


def _windsurf_path() -> Path:
    return Path.home() / ".codeium" / "windsurf" / "mcp_config.json"


def _walk_up_for(start: Path, parts: tuple[str, ...]) -> Optional[Path]:
    """
    Walk up from `start` looking for start/<parts[0]>/.../<parts[-1]>.
    Returns the first match, or None if we hit the filesystem root.
    """
    current = start.resolve()
    while True:
        candidate = current.joinpath(*parts)
        if candidate.exists():
            return candidate
        parent = current.parent
        if parent == current:
            return None
        current = parent


# ---------------------------------------------------------------------------
# Env var substitution
# ---------------------------------------------------------------------------

def _resolve_env_refs(value: str, env: dict[str, str]) -> str:
    """Replace ${VAR} / $VAR with values from `env`. Unresolved → pass through."""
    def repl(m: re.Match) -> str:
        name = m.group(1) or m.group(2)
        return env.get(name, m.group(0))
    return _ENV_REF.sub(repl, value)


def _resolve_dict(d: dict[str, str], env: dict[str, str]) -> dict[str, str]:
    return {k: _resolve_env_refs(v, env) for k, v in d.items() if isinstance(v, str)}


def _resolve_list(lst: list, env: dict[str, str]) -> list[str]:
    out = []
    for item in lst:
        if isinstance(item, str):
            out.append(_resolve_env_refs(item, env))
        else:
            # Non-string args are unusual but we pass them through as str so
            # the model stays happy. MCP config spec expects strings.
            out.append(str(item))
    return out


# ---------------------------------------------------------------------------
# Shape parsing — mcpServers → MCPServer
# ---------------------------------------------------------------------------

def _parse_claude_json(raw: dict, source_path: str, env=None) -> list[MCPServer]:
    """
    ~/.claude.json nests mcpServers under raw["projects"][<project-path>]["mcpServers"]
    """
    servers = []
    projects = raw.get("projects")
    if not isinstance(projects, dict):
        return servers
    for project_path, value in projects.items():
        if not isinstance(value, dict):
            continue
        if "mcpServers" in value:
            servers.extend(_parse_mcp_servers(value, source_path, env=env))
    return servers

def _read_claude_json(
    env: Optional[dict[str, str]] = None,
) -> Optional[DiscoverySource]:
    path = _claude_code_user_path()
    path_str = str(path)
    client = "claude_code_user_path"

    if not path.exists():
        return DiscoverySource(client=client, path=path_str, status=SourceStatus.NOT_FOUND)

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return DiscoverySource(client=client, path=path_str, status=SourceStatus.READ_ERROR, error=str(exc))

    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        return DiscoverySource(client=client, path=path_str, status=SourceStatus.PARSE_ERROR,
                               error=f"Invalid JSON at line {exc.lineno}: {exc.msg}")

    if not isinstance(raw, dict):
        return DiscoverySource(client=client, path=path_str, status=SourceStatus.PARSE_ERROR,
                               error=f"Expected object, got {type(raw).__name__}")

    servers = _parse_claude_json(raw, path_str, env=env)
    status = SourceStatus.FOUND if servers else SourceStatus.EMPTY
    return DiscoverySource(client=client, path=path_str, status=status, servers=servers)

def _parse_mcp_servers(
    raw: dict,
    source_path: str,
    env: Optional[dict[str, str]] = None,
) -> list[MCPServer]:
    """
    Extract `mcpServers` block into a list of MCPServer instances.

    `raw` is the already-loaded JSON dict. Missing / malformed entries are
    logged and skipped rather than raising — one bad server shouldn't take
    the whole config down.
    """
    env = env if env is not None else dict(os.environ)
    mcp_servers = raw.get("mcpServers")
    if not isinstance(mcp_servers, dict):
        return []

    results: list[MCPServer] = []
    for server_id, spec in mcp_servers.items():
        if not isinstance(spec, dict):
            logger.warning(
                "Skipping server %r in %s: expected object, got %s",
                server_id, source_path, type(spec).__name__,
            )
            continue

        try:
            server = _spec_to_server(server_id, spec, env)
        except Exception as exc:
            logger.warning(
                "Skipping server %r in %s: %s", server_id, source_path, exc,
            )
            continue

        results.append(server)

    return results


def _spec_to_server(server_id: str, spec: dict, env: dict[str, str]) -> MCPServer:
    """Build one MCPServer from one mcpServers entry."""
    command = spec.get("command")
    url = spec.get("url")
    args_raw = spec.get("args") or []
    env_raw = spec.get("env") or {}
    description = spec.get("description")  # non-standard but some configs carry it

    # Transport inference
    if command:
        transport = "stdio"
    elif url:
        # Can't distinguish sse vs streamable-http from config alone —
        # streamable-http is the newer default but sse is what most existing
        # configs use. Default to sse; the MCP client (Phase 1 #3) will
        # confirm by probing.
        transport = spec.get("type") or spec.get("transport") or "sse"
    else:
        raise ValueError("server has neither `command` nor `url`")

    if command:
        command = _resolve_env_refs(command, env)
    if url:
        url = _resolve_env_refs(url, env)
    args = _resolve_list(args_raw, env) if isinstance(args_raw, list) else []
    resolved_env = _resolve_dict(env_raw, env) if isinstance(env_raw, dict) else {}

    return MCPServer(
        id=server_id,
        name=server_id,                 # name defaults to id; UI can override later
        transport=transport,
        command=command,
        args=args,
        env=resolved_env,
        url=url,
        description=description,
    )


# ---------------------------------------------------------------------------
# Per-client readers
# ---------------------------------------------------------------------------

def _read_one(
    client: str,
    path: Optional[Path],
    env: Optional[dict[str, str]] = None,
) -> Optional[DiscoverySource]:
    """
    Read one config file and return a DiscoverySource.

    Returns None when `path` is None (i.e. path resolution itself came up
    empty — e.g. no .claude/settings.json anywhere up the tree). That lets
    the caller skip recording sources that were never applicable.
    """
    if path is None:
        return None

    path_str = str(path)

    if not path.exists():
        return DiscoverySource(client=client, path=path_str, status=SourceStatus.NOT_FOUND)

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return DiscoverySource(
            client=client, path=path_str, status=SourceStatus.READ_ERROR,
            error=str(exc),
        )

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

    servers = _parse_mcp_servers(raw, path_str, env=env)
    if not servers:
        return DiscoverySource(
            client=client, path=path_str, status=SourceStatus.EMPTY,
        )

    return DiscoverySource(
        client=client, path=path_str, status=SourceStatus.FOUND, servers=servers,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

# Each entry: (client_id, path_resolver). Resolvers that need cwd close over it.
def _build_plan(cwd: Path) -> list[tuple[str, Callable[[], Optional[Path]]]]:
    return [
        ("claude_desktop",       _claude_desktop_path),
        ("claude_code_project",  lambda: _claude_code_project_path(cwd)),
        # ("claude_code_user",     _claude_code_user_path),
        ("cursor_project",       lambda: _cursor_project_path(cwd)),
        ("cursor_user",          _cursor_user_path),
        ("windsurf",             _windsurf_path),
    ]


def detect_all(
    cwd: Optional[Path] = None,
    env: Optional[dict[str, str]] = None,
    custom_paths: Optional[list[Path]] = None,
    auto_detect: bool = True,
) -> ConfigDetectionResult:
    """
    Check config locations and return an aggregate of discovered servers.

    Parameters
    ----------
    cwd : Path, optional
        Directory from which to search for project-local configs
        (.cursor/mcp.json, .claude/settings.json). Defaults to Path.cwd().
        Has no effect when `auto_detect=False`.
    env : dict, optional
        Environment to use when resolving ${VAR} references. Defaults to
        os.environ.
    custom_paths : list[Path], optional
        Explicit paths to MCP config files. Each is read with the same
        parser as the built-in locations and appears in `result.sources`
        with `client="custom"`. Processed BEFORE built-in locations so
        user-specified configs win on duplicate server IDs.

        A custom path that doesn't exist or can't be parsed does NOT
        crash — it's recorded as a failed DiscoverySource so the caller
        (e.g. CLI) can surface the problem without aborting the rest.
    auto_detect : bool
        When False, the 6 built-in client locations are skipped entirely
        and only `custom_paths` are read. Useful for hermetic tests and
        CI runs that should only consider an explicit manifest.

    Returns
    -------
    ConfigDetectionResult
        Holds one DiscoverySource per location checked, plus the
        deduplicated union of MCPServer instances. First sighting wins
        on conflicts; custom configs always come first when both flags
        are used together.
    """
    cwd = cwd or Path.cwd()
    result = ConfigDetectionResult()

    # ── 1. Custom paths — always processed first if provided ─────────────────
    if custom_paths:
        for raw_path in custom_paths:
            path = Path(raw_path).expanduser().resolve()
            source = _read_one("custom", path, env=env)
            # _read_one only returns None when path is None (which can't
            # happen here), so source is always a DiscoverySource.
            assert source is not None
            result.sources.append(source)
            _merge_servers(result, source, client="custom")

    # ── 2. Built-in locations ────────────────────────────────────────────────
    if auto_detect:

        source = _read_claude_json(env=env)
        if source is not None:
            result.sources.append(source)
            _merge_servers(result, source, client="claude_code_user")
        plan = _build_plan(cwd)
        priority_index = {c: i for i, c in enumerate(_CLIENT_PRIORITY)}
        plan.sort(key=lambda item: priority_index.get(item[0], 999))

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

    return result


def _merge_servers(
    result: ConfigDetectionResult,
    source: DiscoverySource,
    client: str,
) -> None:
    """
    Merge a source's servers into `result.servers`, recording duplicates.
    First-sighting-wins rule — the caller controls ordering.
    """
    for server in source.servers:
        if server.id in result.servers:
            prior_client = _owner_of(result, server.id)
            result.duplicates.append(
                f"{client}:{server.id} already defined by {prior_client}"
            )
            continue
        result.servers[server.id] = server


def _owner_of(result: ConfigDetectionResult, server_id: str) -> str:
    """Which client contributed this server? Used only for duplicate notes."""
    for src in result.sources:
        if any(s.id == server_id for s in src.servers):
            return src.client
    return "unknown"