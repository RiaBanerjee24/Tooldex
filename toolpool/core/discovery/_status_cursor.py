"""
toolpool/core/discovery/_status_cursor.py

Live status enrichment for Cursor servers via `cursor-agent mcp list-tools`.

Two-step probe:
  1. cursor-agent mcp list          — discover server names
  2. cursor-agent mcp list-tools <n> — probe each server concurrently (4 workers)

Status values:
  "enabled"  — list-tools returned a tool listing ("Tools for <name> (N):")
  "disabled" — list-tools ran but returned no tool listing
"""
from __future__ import annotations

import re
import subprocess
from concurrent.futures import ThreadPoolExecutor


def fetch_cursor_status() -> dict[str, tuple[str, str]]:
    """Return {server_name: (status, raw_string)}."""
    try:
        proc = subprocess.run(
            ["cursor-agent", "mcp", "list"],
            capture_output=True, text=True, timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return {}

    names: list[str] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line or ": " not in line:
            continue
        name = line.partition(": ")[0].strip()
        if name:
            names.append(name)

    if not names:
        return {}

    result: dict[str, tuple[str, str]] = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for name, entry in pool.map(_probe_one, names):
            result[name] = entry
    return result


def _probe_one(name: str) -> tuple[str, tuple[str, str]]:
    try:
        tp = subprocess.run(
            ["cursor-agent", "mcp", "list-tools", name],
            capture_output=True, text=True, timeout=15,
        )
        out = tp.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return name, ("discovered", "discovered")

    first = out.split("\n")[0] if out else ""
    if re.match(rf"tools for {re.escape(name.lower())}\s*\(", first.lower()):
        m = re.search(r"\((\d+)\)", first)
        count = m.group(1) if m else "?"
        return name, ("enabled", f"{count} tools")
    return name, ("disabled", first or "no output")
