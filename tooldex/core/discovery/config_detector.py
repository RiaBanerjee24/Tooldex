"""
tooldex/core/discovery/config_detector.py

Orchestrates MCP config-file autodiscovery.

Delegates to:
  _readers.py        — file I/O (JSON / TOML config readers)
  _parsers.py        — env resolution and mcpServers shape parsing
  _paths.py          — platform-aware path resolution
  _status_claude.py  — live status via `claude mcp list`
  _status_cursor.py  — live status via `cursor-agent mcp list-tools`
  _status_codex.py   — live status via `codex mcp list`
  _docker_mcp.py     — Docker MCP Toolkit profile reader
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Optional

from tooldex.core.discovery._readers import read_json, read_claude_json, read_codex_toml
from tooldex.core.discovery._paths import (
    CLIENT_PRIORITY,
    build_plan,
    codex_project_path,
    codex_user_path,
)
from tooldex.core.discovery._status_claude import fetch_claude_status
from tooldex.core.discovery._status_cursor import fetch_cursor_status
from tooldex.core.discovery._status_codex import fetch_codex_status
from tooldex.core.discovery._docker_mcp import read_all_docker_mcp_profiles
from tooldex.core.discovery.results import ConfigDetectionResult, DiscoverySource

logger = logging.getLogger("tooldex.discovery.config")


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
    Discover MCP servers from all known config locations and return an
    aggregate ConfigDetectionResult with live status enrichment.

    Parameters
    ----------
    cwd             Directory from which to search for project-local configs.
                    Defaults to Path.cwd().
    env             Environment for resolving ${VAR} references.
    custom_paths    Explicit config file paths. Processed before built-in
                    locations so they win on duplicate server IDs.
    auto_detect     When False, skip built-in client locations entirely.
    allow_*_status  Permission flags for each live-status CLI call.
    """
    cwd = cwd or Path.cwd()
    result = ConfigDetectionResult()

    # ── 1. Custom paths ───────────────────────────────────────────────────────
    for raw_path in (custom_paths or []):
        path = Path(raw_path).expanduser().resolve()
        source = read_json("custom", path, env=env)
        if source is None:
            continue
        result.sources.append(source)
        _merge(result, source, client="custom")

    if not auto_detect:
        return result

    # ── 2. Claude Code global (~/.claude.json) ────────────────────────────────
    source = read_claude_json(cwd, env=env)
    if source is not None:
        result.sources.append(source)
        _merge(result, source, client="claude_code_user")

    # ── 3. Codex project (<project>/.codex/config.toml) ──────────────────────
    project_codex = codex_project_path(cwd)
    if project_codex is not None:
        source = read_codex_toml(project_codex, client="codex_project", env=env)
        result.sources.append(source)
        _merge(result, source, client="codex_project")

    # ── 4. Codex global (~/.codex/config.toml) ───────────────────────────────
    source = read_codex_toml(codex_user_path(), client="codex", env=env)
    result.sources.append(source)
    _merge(result, source, client="codex")

    # ── 5. JSON-based clients (Claude Desktop, Claude Code project, Cursor, Windsurf, MCP JSON)
    priority_index = {c: i for i, c in enumerate(CLIENT_PRIORITY)}
    plan = sorted(build_plan(cwd), key=lambda item: priority_index.get(item[0], 999))

    for client, resolver in plan:
        try:
            path = resolver()
        except Exception as exc:
            logger.warning("Path resolution failed for %s: %s", client, exc)
            continue

        source = read_json(client, path, env=env)
        if source is None:
            continue
        result.sources.append(source)
        _merge(result, source, client=client)

    # ── 6. Docker MCP Toolkit profiles ───────────────────────────────────────
    for source in read_all_docker_mcp_profiles():
        result.sources.append(source)
        _merge(result, source, client=source.client)

    # ── 7. Enrich Claude servers with live status ─────────────────────────────
    if allow_claude_status:
        project_dirs = _collect_claude_project_dirs(result)
        claude_statuses = fetch_claude_status(cwd=cwd, project_dirs=project_dirs)
        for qid, server in result.servers.items():
            if server.client and server.client.startswith("claude_code"):
                status = claude_statuses.get(server.name)
                if status:
                    result.servers[qid] = server.model_copy(
                        update={"connection_status": status, "raw_connection_status": status}
                    )

    # ── 8. Enrich Codex servers with live status ──────────────────────────────
    if allow_codex_status:
        codex_statuses = fetch_codex_status()
        for qid, server in result.servers.items():
            if server.client and server.client.startswith("codex"):
                status = codex_statuses.get(server.name)
                if status:
                    result.servers[qid] = server.model_copy(
                        update={"connection_status": status, "raw_connection_status": status}
                    )

    # ── 9. Enrich Cursor servers with live status ─────────────────────────────
    if allow_cursor_status:
        cursor_statuses = fetch_cursor_status()
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
# Internal helpers
# ---------------------------------------------------------------------------

def _collect_claude_project_dirs(result: ConfigDetectionResult) -> set[Path]:
    """
    Collect unique project directories to run `claude mcp list` from.

    Two sources:
    - project_path: set on servers from ~/.claude.json project entries
    - source_path parent: for servers from local .claude.json files
    """
    _home_claude = str(Path.home() / ".claude.json")
    dirs: set[Path] = set()

    for server in result.servers.values():
        if not (server.client and server.client.startswith("claude_code")):
            continue
        if server.project_path:
            try:
                p = Path(server.project_path)
                if p.exists():
                    dirs.add(p)
            except Exception:
                pass
        elif (server.client == "claude_code_project"
              and server.source_path
              and server.source_path != _home_claude):
            try:
                p = Path(server.source_path).parent
                if p.exists():
                    dirs.add(p)
            except Exception:
                pass

    return dirs


def _project_slug(project_path: str) -> str:
    """Short URL-safe hash of a project path (avoids slashes in qualified IDs)."""
    return hashlib.md5(project_path.encode()).hexdigest()[:10]


def _merge(
    result: ConfigDetectionResult,
    source: DiscoverySource,
    client: str,
) -> None:
    """
    Merge a source's servers into result using qualified IDs.

    ID rules:
    - Global:  "{client}:{server_id}"
    - Project: "{client}:{project_slug}:{server_id}"   (MD5 slug, no slashes)

    Project servers from ~/.claude.json (client=claude_code_user) are
    remapped to claude_code_project so the UI groups them correctly.
    First-sighting wins on duplicate IDs.

    Populates result.duplicates with:
    - Cross-client name collisions: same server name seen in multiple clients.
    - In-file duplicate JSON keys reported by the reader.
    """
    for dup_key in source.in_file_duplicates:
        result.duplicates.append(
            f'"{dup_key}" is a duplicate key in {source.path} (last value kept)'
        )

    for server in source.servers:
        if client == "claude_code_user" and server.project_path:
            effective_client = "claude_code_project"
            slug = _project_slug(server.project_path)
            qualified_id = f"{effective_client}:{slug}:{server.id}"
        else:
            effective_client = client
            qualified_id = f"{effective_client}:{server.id}"

        if qualified_id not in result.servers:
            result.servers[qualified_id] = server.model_copy(update={
                "client": effective_client,
                "id": qualified_id,
                "source_path": source.path,
            })
            name = server.name or server.id
            if name in result._name_to_qid:
                first_client = result.servers[result._name_to_qid[name]].client or "unknown"
                result.duplicates.append(
                    f'"{name}" in {effective_client} is also configured in {first_client}'
                )
            else:
                result._name_to_qid[name] = qualified_id
        else:
            existing_client = result.servers[qualified_id].client or client
            result.duplicates.append(
                f"{client}:{server.id} already defined by {existing_client}"
            )
