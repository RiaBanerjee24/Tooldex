"""
tooldex/core/discovery/probe_cache.py

Per-server probe result cache with TTL.

Stored at ~/.tooldex/probe_cache.json, keyed by a 20-char SHA-256 prefix of
the server's immutable config (command, args, url, transport, env key names).
Results are valid for DEFAULT_TTL seconds (5 minutes) by default.

Avoids re-probing unchanged servers on repeated `tooldex run` invocations.
Use `invalidate(server)` to force a live probe on the next call.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from tooldex.core.discovery.results import ToolDiscoveryResult
    from tooldex.core.models.server import MCPServer

logger = logging.getLogger("tooldex.discovery.cache")

_CACHE_PATH = Path.home() / ".tooldex" / "probe_cache.json"
DEFAULT_TTL: float = 300.0  # 5 minutes
_MAX_ENTRIES = 2_000


def _server_key(server: "MCPServer") -> str:
    sig = json.dumps(
        {
            "command": server.command,
            "args": list(server.args or []),
            "url": str(server.url) if server.url else None,
            "transport": server.transport,
            "env_keys": sorted((server.env or {}).keys()),
        },
        sort_keys=True,
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
        logger.debug("Could not persist probe cache: %s", exc)


def get_cached(
    server: "MCPServer",
    ttl: float = DEFAULT_TTL,
) -> Optional["ToolDiscoveryResult"]:
    """Return a cached ToolDiscoveryResult if it exists and is not stale, else None."""
    cache = _load()
    entry = cache.get(_server_key(server))
    if not entry:
        return None
    if time.time() - entry.get("ts", 0) > ttl:
        return None

    from tooldex.core.discovery.results import DiscoveredTool, ToolDiscoveryResult, ToolDiscoveryStatus
    try:
        tools = [DiscoveredTool(**t) for t in entry.get("tools", [])]
        return ToolDiscoveryResult(
            server_id=entry["server_id"],
            status=ToolDiscoveryStatus(entry["status"]),
            tools=tools,
            error=entry.get("error"),
            duration_ms=entry.get("duration_ms"),
        )
    except Exception as exc:
        logger.debug("Malformed cache entry for %s: %s", server.id, exc)
        return None


def put_cached(server: "MCPServer", result: "ToolDiscoveryResult") -> None:
    """Write a probe result to the cache, evicting oldest entries if over cap."""
    cache = _load()
    key = _server_key(server)
    cache[key] = {
        "server_id": result.server_id,
        "status": result.status.value,
        "tools": [
            {
                "name": t.name,
                "server_id": t.server_id,
                "description": t.description,
                "input_schema": t.input_schema,
            }
            for t in result.tools
        ],
        "error": result.error,
        "duration_ms": result.duration_ms,
        "ts": time.time(),
    }
    if len(cache) > _MAX_ENTRIES:
        sorted_items = sorted(cache.items(), key=lambda kv: kv[1].get("ts", 0))
        cache = dict(sorted_items[-_MAX_ENTRIES:])
    _save(cache)


def invalidate(server: "MCPServer") -> None:
    """Remove a server's cached entry so the next probe is always live."""
    cache = _load()
    key = _server_key(server)
    if key in cache:
        del cache[key]
        _save(cache)
