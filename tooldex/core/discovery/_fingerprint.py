"""
tooldex/core/discovery/_fingerprint.py

Shared content fingerprint for an MCPServer's spawn/connection configuration.

Used by both probe_cache.py (cache invalidation on config change) and
trust_store.py (pinning an approval decision to the exact invocation, so
editing a server's command/args/env after approval is treated as a brand
new, unapproved server rather than silently still-trusted).
"""
from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tooldex.core.models.server import MCPServer


def server_key(server: "MCPServer") -> str:
    """20-char SHA-256 prefix over the server's immutable spawn config."""
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
