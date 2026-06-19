"""
toolpool/core/discovery/_status_codex.py

Live status enrichment for Codex servers via `codex mcp list`.

Parses the fixed-width table output, reading the Status column position
from each section header so column shifts between stdio/HTTP sections are
handled correctly.

  Name        Command  Args  ...  Status   Auth
  MCP_DOCKER  docker   ...        enabled  Unsupported

"enabled" → "connected"; anything else → "failed".
"""
from __future__ import annotations

import subprocess


def fetch_codex_status() -> dict[str, str]:
    """Return {server_name: status}."""
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
