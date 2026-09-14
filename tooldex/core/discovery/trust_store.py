"""
tooldex/core/discovery/trust_store.py

Approval gate for stdio MCP servers.

Tooldex has to spawn a stdio server's `command` to get its tool list — that's
inherent to the MCP stdio transport, there's no way to enumerate tools
without running the process. This module is the consent layer in front of
that: a stdio server is only ever probed once its exact invocation has been
explicitly approved.

Stored at ~/.tooldex/trust_store.json, keyed by `_fingerprint.server_key()`
— a hash of (command, args, transport, env key names). Pinning to that
fingerprint rather than to the server's name/id means editing a config
file's command/args after approval produces a new key: the edited server is
treated as brand new and unapproved, not silently still-trusted.

Each entry also carries `approved_tools` — a snapshot of the tool list from
the first successful probe after approval — so a later probe can detect
when an already-approved server's actual behavior drifts (e.g. an unpinned
`npx`/`uvx` package updating upstream) without needing a second, separate
cache. See record_probe_result().

For a command that runs a local script file directly (`python script.py`,
`node ./server.js`, or an extensionless script as `command` itself), that
tool-list check has a gap: editing the script's body without touching its
declared tool names/descriptions/schemas produces an identical tools/list
response, so nothing looks different — even though the code that runs is
not what was reviewed. `file_hashes` closes that gap for the local-file
case: hashes of the entry script's bytes *and* every other recognized
source file in its directory tree (a server is rarely one file — an entry
point importing a sibling module is the common case, see _project_files),
captured at approval time and checked *before* anything is spawned on every
subsequent probe (mcp_client.py's probe_server calls
files_changed_since_approval() first). A mismatch never executes the
server — it serves the last-known (pre-edit) tool snapshot instead and
flags the server "changed", the same outcome as a tools/list drift detected
the ordinary way. Re-approval (set_decision(..., "allow")) is what accepts
the current files/tool-list as the new baseline; there is no separate
interactive re-prompt for this case. This only applies when a local script
path is actually part of the invocation — package-manager-launched commands
(`npx`, `uvx`) have no single local file to pin and rely on the tools/list
check alone.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Optional

from tooldex.core.discovery._fingerprint import server_key

if TYPE_CHECKING:
    from tooldex.core.discovery.results import DiscoveredTool
    from tooldex.core.models.server import MCPServer

logger = logging.getLogger("tooldex.discovery.trust")

_STORE_PATH = Path.home() / ".tooldex" / "trust_store.json"

Decision = Literal["allow", "deny"]


def _load() -> dict:
    if not _STORE_PATH.exists():
        return {}
    try:
        return json.loads(_STORE_PATH.read_text())
    except Exception:
        return {}


def _save(store: dict) -> None:
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _STORE_PATH.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(store, indent=2))
        tmp.replace(_STORE_PATH)
    except Exception as exc:
        logger.debug("Could not persist trust store: %s", exc)


def get_decision(server: "MCPServer") -> Optional[Decision]:
    """
    Return the raw stored decision for this exact server config, or None if
    never decided. Does not look at file hashes — an "allow" here means
    "approved at some point", not "still matches disk right now". Callers
    that need to know whether it's safe to actually execute must also check
    files_changed_since_approval() (mcp_client.probe_server does this).
    """
    entry = _load().get(server_key(server))
    if not entry:
        return None
    decision = entry.get("decision")
    return decision if decision in ("allow", "deny") else None


def files_changed_since_approval(server: "MCPServer") -> bool:
    """
    True when this server has a stored "allow" decision whose local script
    file(s) no longer hash the same as recorded. This is the pre-execution
    gate: mcp_client.probe_server checks it before every spawn and, on a
    mismatch, never executes — it serves the last-known tool snapshot and
    reports the server as "changed" instead. Re-derived from the live
    server config on every call rather than trusting only what's stored, so
    an approval written before file-hash pinning existed (no `file_hashes`
    key at all) is correctly flagged the first time it's checked, rather
    than silently never being checked again.
    """
    entry = _load().get(server_key(server))
    if not entry or entry.get("decision") != "allow":
        return False
    return not _files_match(server, entry.get("file_hashes") or {})


def clear_all() -> None:
    """Wipe every stored trust decision. Used when a fresh Tooldex install is detected."""
    try:
        _STORE_PATH.unlink(missing_ok=True)
    except OSError as exc:
        logger.debug("Could not clear trust store: %s", exc)


def set_decision(server: "MCPServer", decision: Decision, server_name: Optional[str] = None) -> None:
    """
    Record an approve/deny decision for this server's exact invocation.

    Approving always resets `approved_tools` to None so the next successful
    probe re-baselines against whatever tools that server reports now — this
    is also how re-approving a drifted ("changed") server works: the next
    probe's tool list simply becomes the new accepted baseline.
    """
    store = _load()
    key = server_key(server)
    now = time.time()
    existing = store.get(key, {})
    store[key] = {
        "decision": decision,
        "server_name": server_name or existing.get("server_name") or server.name,
        "approved_tools": None if decision == "allow" else existing.get("approved_tools"),
        "file_hashes": _file_hashes(server) if decision == "allow" else existing.get("file_hashes", {}),
        "decided_at": existing.get("decided_at", now),
        "updated_at": now,
    }
    _save(store)


def remove_decision(server: "MCPServer") -> None:
    """Revoke any stored decision for this server, returning it to 'pending'."""
    store = _load()
    key = server_key(server)
    if key in store:
        del store[key]
        _save(store)


def get_approved_tools(server: "MCPServer") -> Optional[list[dict]]:
    """Return the stored baseline tool snapshot for this server, or None if unset/unapproved."""
    entry = _load().get(server_key(server))
    if not entry or entry.get("decision") != "allow":
        return None
    return entry.get("approved_tools")


def record_probe_result(server: "MCPServer", tools: list["DiscoveredTool"]) -> bool:
    """
    Record a successful probe's tool list against the stored approval.

    Returns True if this server was previously approved with a baseline
    already captured and the fresh tool list no longer matches it (i.e. the
    server's behavior drifted since approval). Returns False when there's no
    "allow" decision on file (nothing to compare against), when this is the
    first probe since approval (the baseline is captured now, not compared),
    or when the fresh list matches the stored baseline.
    """
    store = _load()
    key = server_key(server)
    entry = store.get(key)
    if not entry or entry.get("decision") != "allow":
        return False

    fresh = snapshot_tools(tools)
    baseline = entry.get("approved_tools")
    if baseline is None:
        entry["approved_tools"] = fresh
        entry["updated_at"] = time.time()
        _save(store)
        return False

    return fresh != baseline


def diff_tools(approved: list[dict], current: list[dict]) -> list[dict]:
    """
    Compare two tool snapshots (as stored/produced by snapshot_tools) and return
    a list of {tool, change, before, after} entries: change is "added",
    "removed", or "changed" (description/input_schema differs).
    """
    by_name_before = {t["name"]: t for t in (approved or [])}
    by_name_after = {t["name"]: t for t in (current or [])}

    diffs = []
    for name in sorted(set(by_name_before) | set(by_name_after)):
        before = by_name_before.get(name)
        after = by_name_after.get(name)
        if before is None:
            diffs.append({"tool": name, "change": "added", "before": None, "after": after})
        elif after is None:
            diffs.append({"tool": name, "change": "removed", "before": before, "after": None})
        elif before != after:
            diffs.append({"tool": name, "change": "changed", "before": before, "after": after})
    return diffs


# ---------------------------------------------------------------------------
# Local script file pinning
# ---------------------------------------------------------------------------

_SCRIPT_SUFFIXES = {".py", ".js", ".mjs", ".cjs", ".ts", ".sh", ".rb", ".pl", ".php", ".lua"}


def _resolve_candidate(candidate: str, server: "MCPServer") -> Optional[Path]:
    """
    Resolve a command/arg string to an existing local file, if it is one.

    Tries relative to Tooldex's own process cwd first — that's how the
    actual spawn resolves a relative path, since StdioServerParameters sets
    no explicit cwd of its own. But a relative path in someone's .mcp.json
    is written relative to *that config file*, not to wherever `tooldex`
    happens to be launched from — those are frequently different
    directories. Falling back to the config's own directory means a
    same-directory `"args": ["server.py"]` still resolves (and therefore
    still gets pinned) even when tooldex was started from elsewhere.
    """
    p = Path(candidate)
    if p.is_file():
        return p
    if server.source_path:
        alt = Path(server.source_path).parent / candidate
        if alt.is_file():
            return alt
    return None


def _local_script_paths(server: "MCPServer") -> list[Path]:
    """
    Local files this stdio server's invocation directly executes, if any.

    A candidate qualifies if it resolves to an existing file (see
    _resolve_candidate) and is either the command itself (covers
    extensionless scripts run directly, e.g. `./run`) or has a recognized
    script extension (covers `python script.py`, `node ./server.js`, etc.).
    Package-manager launches like `npx -y pkg` or `uvx pkg` have no such
    local file and yield [].
    """
    if (server.transport or "stdio").lower() != "stdio":
        return []
    candidates = [server.command, *(server.args or [])]
    paths = []
    for i, candidate in enumerate(candidates):
        if not candidate:
            continue
        resolved = _resolve_candidate(candidate, server)
        if resolved is None:
            continue
        if i == 0 or resolved.suffix in _SCRIPT_SUFFIXES:
            paths.append(resolved)
    return paths


_PRUNE_DIR_NAMES = {
    ".git", "__pycache__", "node_modules", ".venv", "venv", "env",
    ".mypy_cache", ".pytest_cache", ".tox", ".idea", ".vscode",
}
# A real MCP server's own source is typically a handful to a few dozen
# files. 500 is already generous headroom for that — it exists to bound
# worst-case cost when this repeats across several approved servers on
# every probe, not to accommodate large legitimate trees (see
# _file_signature/_file_matches_recorded for why the steady-state cost is
# much cheaper than "read every file" regardless of this cap).
_MAX_PROJECT_FILES = 500


def _project_files(server: "MCPServer") -> list[Path]:
    """
    Every local source file reachable by walking *down* from each entry
    point's own directory — not just the entry point script itself.

    A real server is rarely one file: `server.py` importing a sibling
    `tools_impl.py`, or a small `tools/` subpackage next to it, are both
    common, and both invisible to hashing the entry point alone — its bytes
    don't change even though the code that actually runs does. Walking down
    from wherever each entry point lives (rather than up to some inferred
    "project root", which is ambiguous and could land in an arbitrarily
    large unrelated directory) keeps this bounded and unsurprising: it
    covers exactly the directory tree the entry point already lives in.
    Vendor/metadata directories (dependencies, VCS, caches) are excluded —
    pinning an entire node_modules tree is a different, impractical problem,
    the same shape as not being able to pin what `npx` pulls from a registry.
    `_MAX_PROJECT_FILES` is a safety valve for a pathologically large tree,
    not the expected case for an MCP server's own source.
    """
    entry_points = _local_script_paths(server)
    if not entry_points:
        return []

    files: list[Path] = list(entry_points)
    seen = {p.resolve() for p in entry_points}

    # Only walk directories for entry points that look like the server's own
    # script (a recognized source extension) — not a bare interpreter binary
    # picked up via the "command itself is a file" rule (e.g. `command`
    # resolving to `.venv/bin/python3`). An interpreter's own directory
    # (venv bin/, system bin/) isn't the server's project and walking it
    # would sweep in unrelated files that happen to sit next to it.
    for root_dir in {p.parent for p in entry_points if p.suffix in _SCRIPT_SUFFIXES}:
        if not root_dir.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(root_dir):
            dirnames[:] = [d for d in dirnames if d not in _PRUNE_DIR_NAMES and not d.startswith(".")]
            for fname in filenames:
                if Path(fname).suffix not in _SCRIPT_SUFFIXES:
                    continue
                fpath = Path(dirpath) / fname
                resolved = fpath.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                files.append(fpath)
                if len(files) >= _MAX_PROJECT_FILES:
                    logger.warning(
                        "Local script tree for %r has %d+ files — pinning capped, "
                        "some files may not be tracked for drift.",
                        server.name, _MAX_PROJECT_FILES,
                    )
                    return files
    return files


def _hash_file(path: Path) -> Optional[str]:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _file_record(path: Path) -> Optional[dict]:
    """
    {size, mtime, hash} for one file — the hash is still computed at
    record-write time (approval / rebaseline), since that's a one-off cost.
    The cheap part is on the *read* side (_file_still_matches): most checks
    never need to re-read a file's content at all, see there.
    """
    try:
        stat = path.stat()
        return {"size": stat.st_size, "mtime": stat.st_mtime, "hash": _hash_file(path)}
    except OSError:
        return None


def _file_hashes(server: "MCPServer") -> dict[str, dict]:
    records = {}
    for p in _project_files(server):
        rec = _file_record(p)
        if rec is not None:
            records[str(p)] = rec
    return records


def _file_still_matches(path_str: str, recorded: Optional[dict]) -> bool:
    """
    True if one file still matches what was recorded for it.

    Stat first: if size and mtime are unchanged, trust the previously
    recorded hash without touching the file's content at all — this is what
    keeps the steady state (nothing edited) cheap regardless of how many
    files or approved servers there are, since a stat() call is metadata-
    only, no disk read proportional to file size. Only when size or mtime
    actually differ do we pay for a real read+hash, to get a definitive
    answer rather than trusting mtime alone (which a bare `touch` or an
    editor's save-without-changes would otherwise misreport as "changed").
    """
    if recorded is None:
        return False
    try:
        stat = Path(path_str).stat()
    except OSError:
        return False  # file gone
    if stat.st_size == recorded.get("size") and stat.st_mtime == recorded.get("mtime"):
        return True
    return _hash_file(Path(path_str)) == recorded.get("hash")


def _files_match(server: "MCPServer", recorded: dict[str, dict]) -> bool:
    """
    True if every local file this server's directory tree contains —
    currently, or at the time it was recorded — still matches what's
    recorded for it (see _file_still_matches for the actual comparison).

    Checks the union of two path sets rather than just the recorded dict's
    keys, to cover two different ways staleness can hide a change:
      - a path recorded at approval time that no longer resolves at all
        (the file was deleted/moved) — _file_still_matches returns False
        for a path that no longer stats;
      - a path _project_files finds *now* that isn't in the recorded dict
        at all — covers a file added since approval (a new sibling module),
        or an entry written before file-hash pinning existed at all (empty/
        missing `file_hashes`), so both self-heal the next time this is
        checked instead of vacuously "passing" forever.
    """
    all_paths = {str(p) for p in _project_files(server)} | set(recorded.keys())
    if not all_paths:
        return True  # nothing this invocation runs locally (e.g. npx/uvx) — nothing to pin
    return all(_file_still_matches(path_str, recorded.get(path_str)) for path_str in all_paths)


def snapshot_tools(tools: list["DiscoveredTool"]) -> list[dict]:
    """Normalize a tool list into the comparable/storable snapshot shape."""
    return sorted(
        (
            {"name": t.name, "description": t.description, "input_schema": t.input_schema}
            for t in tools
        ),
        key=lambda t: t["name"],
    )
