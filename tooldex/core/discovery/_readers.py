"""
tooldex/core/discovery/_readers.py

Low-level config file readers. Each function takes a path (or derives one)
and returns a DiscoverySource — no network calls, no subprocesses.
"""
from __future__ import annotations

import json5
import logging
from pathlib import Path
from typing import Optional

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

from tooldex.core.discovery._parsers import parse_claude_json, parse_mcp_servers
from tooldex.core.discovery._paths import claude_code_user_path
from tooldex.core.discovery.results import DiscoverySource, SourceStatus

logger = logging.getLogger("tooldex.discovery.readers")


def read_json(
    client: str,
    path: Optional[Path],
    env: Optional[dict[str, str]] = None,
) -> Optional[DiscoverySource]:
    """
    Read one JSON MCP config and return a DiscoverySource.
    Returns None when path is None (resolver found nothing applicable).
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

    duplicate_keys: list[str] = []

    def _pairs_hook(pairs: list) -> dict:
        seen: set[str] = set()
        out: dict = {}
        for k, v in pairs:
            if k in seen:
                duplicate_keys.append(k)
            else:
                seen.add(k)
            out[k] = v
        return out

    try:
        raw = json5.loads(text, object_pairs_hook=_pairs_hook)
    except ValueError as exc:
        return DiscoverySource(
            client=client, path=path_str, status=SourceStatus.PARSE_ERROR,
            error=f"Invalid JSON: {exc}",
        )

    if not isinstance(raw, dict):
        return DiscoverySource(
            client=client, path=path_str, status=SourceStatus.PARSE_ERROR,
            error=f"Top-level JSON must be an object, got {type(raw).__name__}",
        )

    if "mcpServers" not in raw:
        return DiscoverySource(
            client=client, path=path_str, status=SourceStatus.EMPTY,
            error='No "mcpServers" key — not an MCP config file',
        )

    if not isinstance(raw["mcpServers"], dict):
        return DiscoverySource(
            client=client, path=path_str, status=SourceStatus.PARSE_ERROR,
            error=f'"mcpServers" must be an object, got {type(raw["mcpServers"]).__name__}',
        )

    servers = parse_mcp_servers(raw, path_str, env=env)
    status = SourceStatus.FOUND if servers else SourceStatus.EMPTY
    return DiscoverySource(
        client=client, path=path_str, status=status, servers=servers,
        in_file_duplicates=duplicate_keys,
    )


def read_claude_json(
    cwd: Path,
    env: Optional[dict[str, str]] = None,
) -> Optional[DiscoverySource]:
    """
    Read ~/.claude.json, returning user-level and walk-up-scoped project servers.
    Project servers are only included if their project_path is on the CWD walk-up path.
    """
    path = claude_code_user_path()
    path_str = str(path)
    client = "claude_code_user"

    if not path.exists():
        return DiscoverySource(client=client, path=path_str, status=SourceStatus.NOT_FOUND)

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return DiscoverySource(client=client, path=path_str, status=SourceStatus.READ_ERROR, error=str(exc))

    duplicate_keys: list[str] = []

    def _pairs_hook(pairs: list) -> dict:
        seen: set[str] = set()
        out: dict = {}
        for k, v in pairs:
            if k in seen:
                duplicate_keys.append(k)
            else:
                seen.add(k)
            out[k] = v
        return out

    try:
        raw = json5.loads(text, object_pairs_hook=_pairs_hook)
    except ValueError as exc:
        return DiscoverySource(
            client=client, path=path_str, status=SourceStatus.PARSE_ERROR,
            error=f"Invalid JSON: {exc}",
        )

    if not isinstance(raw, dict):
        return DiscoverySource(
            client=client, path=path_str, status=SourceStatus.PARSE_ERROR,
            error=f"Expected object, got {type(raw).__name__}",
        )

    servers = parse_claude_json(raw, path_str, cwd, env=env)
    status = SourceStatus.FOUND if servers else SourceStatus.EMPTY
    return DiscoverySource(
        client=client, path=path_str, status=status, servers=servers,
        in_file_duplicates=duplicate_keys,
    )


def read_codex_toml(
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
