"""
toolpool/core/discovery/_status_claude.py

Live status enrichment for Claude Code servers via `claude mcp list`.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional


def fetch_claude_status(
    cwd: Optional[Path] = None,
    project_dirs: Optional[set] = None,
) -> dict[str, str]:
    """
    Return {server_name: status} by running `claude mcp list` from each
    unique directory in {cwd} ∪ project_dirs.

    Deduplicates by resolved path so the same directory is never queried twice
    (avoids hitting remote MCP servers multiple times when project_dirs
    overlaps with cwd).
    """
    resolved_cwd = (Path(cwd) if cwd else Path.cwd()).resolve()

    dirs: set[Path] = {resolved_cwd}
    for d in (project_dirs or set()):
        try:
            p = Path(d).resolve()
            if p.exists():
                dirs.add(p)
        except Exception:
            pass

    statuses: dict[str, str] = {}
    for d in dirs:
        statuses.update(_run_claude_mcp_list(cwd=d))
    return statuses


def _run_claude_mcp_list(cwd: Optional[Path] = None) -> dict[str, str]:
    """Run `claude mcp list` from `cwd` and parse {name: status}."""
    try:
        proc = subprocess.run(
            ["claude", "mcp", "list"],
            capture_output=True, stdin=subprocess.DEVNULL, text=True, timeout=15,
            cwd=str(cwd) if cwd else None,
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
    return statuses
