"""
toolpool/core/discovery/_parsers.py

Environment variable resolution and raw config-shape parsers.

Takes already-loaded JSON/TOML dicts and converts them to MCPServer instances.
No file I/O — that lives in config_detector.py.

Private module — imported only by config_detector.py.

Supported MCP server shape (JSON/TOML):

    {
      "mcpServers": {           // or "mcp_servers" in TOML (Codex)
        "<id>": {
          "command": "npx",     // stdio transport
          "args": [...],
          "env": {...}
        },
        "<id>": {
          "url": "http://...",  // sse / streamable-http
          "type": "sse"
        }
      }
    }

Env var references like ${VAR} or $VAR inside `env` and `args` are resolved
against the process environment. Unresolved references pass through as-is.
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Optional

from toolpool.core.models.server import MCPServer

logger = logging.getLogger("toolpool.discovery.parsers")

_ENV_REF = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)")


# ---------------------------------------------------------------------------
# Env var substitution
# ---------------------------------------------------------------------------

def resolve_env_refs(value: str, env: dict[str, str]) -> str:
    """Replace ${VAR} / $VAR with values from `env`. Unresolved → pass through."""
    def repl(m: re.Match) -> str:
        name = m.group(1) or m.group(2)
        return env.get(name, m.group(0))
    return _ENV_REF.sub(repl, value)


def resolve_dict(d: dict[str, str], env: dict[str, str]) -> dict[str, str]:
    return {k: resolve_env_refs(v, env) for k, v in d.items() if isinstance(v, str)}


def resolve_list(lst: list, env: dict[str, str]) -> list[str]:
    out = []
    for item in lst:
        if isinstance(item, str):
            out.append(resolve_env_refs(item, env))
        else:
            out.append(str(item))
    return out


# ---------------------------------------------------------------------------
# Shape parsing — mcpServers / mcp_servers → MCPServer list
# ---------------------------------------------------------------------------

def parse_mcp_servers(
    raw: dict,
    source_path: str,
    env: Optional[dict[str, str]] = None,
    key: str = "mcpServers",
) -> list[MCPServer]:
    """
    Extract the `mcpServers` (or `key`) block into a list of MCPServer instances.

    Missing / malformed entries are logged and skipped rather than raising —
    one bad server should not take down the whole config.
    `key` lets callers handle configs that nest servers under a different name
    (e.g. Codex CLI uses `mcp_servers`).
    """
    env = env if env is not None else dict(os.environ)
    mcp_servers = raw.get(key)
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
        if spec.get("disabled"):
            logger.debug("Skipping disabled server %r in %s", server_id, source_path)
            continue
        try:
            results.append(_spec_to_server(server_id, spec, env))
        except Exception as exc:
            logger.warning("Skipping server %r in %s: %s", server_id, source_path, exc)

    return results


def _spec_to_server(server_id: str, spec: dict, env: dict[str, str]) -> MCPServer:
    """Build one MCPServer from one mcpServers entry."""
    command = spec.get("command")
    url = spec.get("url")
    args_raw = spec.get("args") or []
    env_raw = spec.get("env") or {}
    description = spec.get("description")

    if command:
        transport = "stdio"
    elif url:
        raw = (spec.get("type") or spec.get("transport") or "").lower().replace("-", "_")
        transport = "sse" if raw == "sse" else "http"
    else:
        raise ValueError("server has neither `command` nor `url`")

    headers_raw = dict(spec.get("headers") or {})

    # Codex stores auth as bearer_token_env_var — either an env var name or a
    # literal token value. Try to resolve as env var first, fall back to literal.
    bearer_ref = spec.get("bearer_token_env_var")
    if bearer_ref and isinstance(bearer_ref, str):
        token = env.get(bearer_ref, bearer_ref)
        headers_raw.setdefault("Authorization", f"Bearer {token}")

    return MCPServer(
        id=server_id,
        name=server_id,
        transport=transport,
        command=resolve_env_refs(command, env) if command else None,
        args=resolve_list(args_raw, env) if isinstance(args_raw, list) else [],
        env=resolve_dict(env_raw, env) if isinstance(env_raw, dict) else {},
        headers=resolve_dict(headers_raw, env) if isinstance(headers_raw, dict) else {},
        url=resolve_env_refs(url, env) if url else None,
        description=description,
    )


def parse_claude_json(
    raw: dict,
    source_path: str,
    cwd: Path,
    env: Optional[dict[str, str]] = None,
) -> list[MCPServer]:
    """
    Parse ~/.claude.json which holds two kinds of mcpServers:

    - Top-level raw["mcpServers"]: user-scoped, apply to every project.
    - raw["projects"][<project-path>]["mcpServers"]: project-scoped, only
      relevant when `cwd` is inside that project.

    We pick the single project entry whose path is `cwd` or the closest
    ancestor of it — Claude Code keys `projects` by absolute project root.
    """
    servers = []

    if isinstance(raw.get("mcpServers"), dict):
        servers.extend(parse_mcp_servers(raw, source_path, env=env))

    projects = raw.get("projects")
    if not isinstance(projects, dict):
        return servers

    cwd = cwd.resolve()
    best_match: Optional[str] = None
    best_depth = -1
    for project_path in projects:
        try:
            p = Path(project_path).resolve()
        except OSError:
            continue
        if cwd != p and p not in cwd.parents:
            continue
        depth = len(p.parts)
        if depth > best_depth:
            best_depth = depth
            best_match = project_path

    if best_match is not None:
        value = projects[best_match]
        if isinstance(value, dict) and "mcpServers" in value:
            servers.extend(parse_mcp_servers(value, source_path, env=env))

    return servers
