"""
toolpool/core/discovery/_paths.py

Platform-aware path resolvers for every supported MCP client config file,
plus the priority ordering used when deduplicating server IDs across sources.

Private module — imported only by config_detector.py.

Scope rules
-----------
Global (user-level) configs live in the home directory and apply machine-wide.
Project-level configs live somewhere inside a project tree (below home).
walk_up_for() stops at the home directory so a project walk-up can never
accidentally return a global config file.

Supported locations:

    Claude Desktop      claude_desktop_config.json
        macOS    ~/Library/Application Support/Claude/claude_desktop_config.json
        Windows  %APPDATA%\\Claude\\claude_desktop_config.json
        Linux    ~/.config/Claude/claude_desktop_config.json

    Claude Code         ~/.claude.json              (global)
                        <project>/.claude/mcp.json  (project, walk up, stops at ~)
                        <project>/.claude.json       (project, flat-file alternative)

    Cursor              ~/.cursor/mcp.json          (global)
                        <project>/.cursor/mcp.json  (project, walk up, stops at ~)

    Windsurf            ~/.codeium/windsurf/mcp_config.json  (global only)

    Codex CLI           ~/.codex/config.toml        (global)
                        <project>/.codex/config.toml (project, walk up, stops at ~)

    MCP JSON            ~/.mcp.json                 (global, team/shared definitions)
                        <project>/.mcp.json          (project, walk up, stops at ~)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Callable, Optional


# Priority order for display / source ordering.
# Project-scoped configs come before their global counterparts.
CLIENT_PRIORITY = (
    "claude_desktop",
    "claude_code_project",
    "claude_code_user",
    "cursor_project",
    "cursor_user",
    "windsurf",
    "codex_project",
    "codex",
    "mcp_json_project",
    "mcp_json_user",
)


def walk_up_for(start: Path, parts: tuple[str, ...]) -> Optional[Path]:
    """
    Walk up from `start` looking for start/<parts[0]>/.../<parts[-1]>.

    Stops at the home directory — files in ~ belong to the global scope,
    not to any project. Returns None if no match is found before home.
    """
    home = Path.home().resolve()
    current = start.resolve()
    while True:
        if current == home:
            return None
        candidate = current.joinpath(*parts)
        if candidate.exists():
            return candidate
        parent = current.parent
        if parent == current:
            return None
        current = parent


def claude_desktop_path() -> Path:
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    if sys.platform.startswith("win"):
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else home / "AppData" / "Roaming"
        return base / "Claude" / "claude_desktop_config.json"
    return home / ".config" / "Claude" / "claude_desktop_config.json"


def claude_code_user_path() -> Path:
    return Path.home() / ".claude.json"


def claude_code_project_path(cwd: Path) -> Optional[Path]:
    # .claude/mcp.json takes precedence; fall back to .claude.json (flat file)
    return walk_up_for(cwd, (".claude", "mcp.json")) or walk_up_for(cwd, (".claude.json",))


def cursor_user_path() -> Path:
    return Path.home() / ".cursor" / "mcp.json"


def cursor_project_path(cwd: Path) -> Optional[Path]:
    return walk_up_for(cwd, (".cursor", "mcp.json"))


def windsurf_path() -> Path:
    return Path.home() / ".codeium" / "windsurf" / "mcp_config.json"


def codex_user_path() -> Path:
    return Path.home() / ".codex" / "config.toml"


def codex_project_path(cwd: Path) -> Optional[Path]:
    return walk_up_for(cwd, (".codex", "config.toml"))


def mcp_json_user_path() -> Path:
    return Path.home() / ".mcp.json"


def mcp_json_project_path(cwd: Path) -> Optional[Path]:
    return walk_up_for(cwd, (".mcp.json",))


def build_plan(cwd: Path) -> list[tuple[str, Callable[[], Optional[Path]]]]:
    """
    Build the list of (client_id, path_resolver) pairs for the standard
    JSON-based clients. Codex (TOML) and Claude Code global (.claude.json)
    are handled separately in config_detector because they need custom parsers.
    """
    return [
        ("claude_desktop",      claude_desktop_path),
        ("claude_code_project", lambda: claude_code_project_path(cwd)),
        ("cursor_project",      lambda: cursor_project_path(cwd)),
        ("cursor_user",         cursor_user_path),
        ("windsurf",            windsurf_path),
        ("mcp_json_project",    lambda: mcp_json_project_path(cwd)),
        ("mcp_json_user",       mcp_json_user_path),
    ]
