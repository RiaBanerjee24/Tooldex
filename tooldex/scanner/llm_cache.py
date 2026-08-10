"""
tooldex/scanner/llm_cache.py

Per-tool LLM-judge scan result cache, stored at ~/.tooldex/llm_scan_cache.json
and keyed by (server_id, tool_name). Each entry is pinned to a hash of the
tool's name + description + input_schema, so a cache hit means that tool is
unchanged since its last judged verdict. No TTL.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("tooldex.scanner.llm_cache")

_CACHE_PATH = Path.home() / ".tooldex" / "llm_scan_cache.json"
_MAX_ENTRIES = 10_000


def _entry_key(server_id: str, tool_name: str) -> str:
    return f"{server_id}::{tool_name}"


def tool_hash(name: str, description: Optional[str], input_schema: Optional[dict]) -> str:
    """Fingerprint of everything about a tool that could change the LLM's verdict."""
    sig = json.dumps(
        {"name": name, "description": description, "input_schema": input_schema},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(sig.encode()).hexdigest()[:20]


def _load() -> dict:
    if not _CACHE_PATH.exists():
        return {}
    try:
        return json.loads(_CACHE_PATH.read_text())
    except Exception:
        return {}


def _save(cache: dict) -> None:
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _CACHE_PATH.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(cache, separators=(",", ":")))
        tmp.replace(_CACHE_PATH)
    except Exception as exc:
        logger.debug("Could not persist LLM scan cache: %s", exc)


def get_cached(server_id: str, tool_name: str, current_hash: str) -> Optional[dict]:
    """Return {"findings": list[dict], "is_safe": bool} for a matching hash, else None."""
    cache = _load()
    entry = cache.get(_entry_key(server_id, tool_name))
    if not entry or entry.get("hash") != current_hash:
        return None
    return {"findings": entry.get("findings", []), "is_safe": entry.get("is_safe", True)}


def put_cached(
    server_id: str,
    tool_name: str,
    current_hash: str,
    findings: list[dict[str, Any]],
    is_safe: bool,
) -> None:
    cache = _load()
    cache[_entry_key(server_id, tool_name)] = {
        "hash": current_hash,
        "findings": findings,
        "is_safe": is_safe,
        "ts": time.time(),
    }
    if len(cache) > _MAX_ENTRIES:
        sorted_items = sorted(cache.items(), key=lambda kv: kv[1].get("ts", 0))
        cache = dict(sorted_items[-_MAX_ENTRIES:])
    _save(cache)


def invalidate_server(server_id: str) -> int:
    """Remove all cached entries for one server. Returns how many were removed."""
    cache = _load()
    prefix = f"{server_id}::"
    remaining = {k: v for k, v in cache.items() if not k.startswith(prefix)}
    removed = len(cache) - len(remaining)
    if removed:
        _save(remaining)
    return removed


def has_entries_for(server_id: str) -> bool:
    """True if any cache entry exists for this server, regardless of hash validity."""
    cache = _load()
    prefix = f"{server_id}::"
    return any(k.startswith(prefix) for k in cache)


def get_all_matching(server_id: str, tools: list) -> dict[str, dict]:
    """
    For manifest hydration at startup: given a server's current discovered
    tools (each with .name/.description/.input_schema), return
    {tool_name: {"findings", "is_safe", "ts"}} for every tool whose cached
    verdict still matches its current identity hash.
    """
    cache = _load()
    result = {}
    for t in tools:
        h = tool_hash(t.name, t.description, t.input_schema)
        entry = cache.get(_entry_key(server_id, t.name))
        if entry and entry.get("hash") == h:
            result[t.name] = {
                "findings": entry.get("findings", []),
                "is_safe": entry.get("is_safe", True),
                "ts": entry.get("ts", 0),
            }
    return result
