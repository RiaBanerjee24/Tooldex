"""
tooldex/core/parsers/parser.py
Module-level singleton holding the active TooldexManifest.
"""
from __future__ import annotations
import logging
from typing import Optional
from tooldex.core.models.manifest import TooldexManifest

logger = logging.getLogger("tooldex.parser")


class TooldexParser:
    def __init__(self, manifest: TooldexManifest):
        self._manifest = manifest

    @property
    def manifest(self) -> TooldexManifest:
        return self._manifest


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_parser: Optional[TooldexParser] = None
_last_scanned: Optional[str] = None    # ISO-8601 UTC, set on every manifest install
_startup_time: Optional[float] = None  # time.monotonic() snapshot for uptime
_discovery_sources: list = []          # DiscoverySource list from last detect_all()


def get_last_scanned() -> Optional[str]:
    return _last_scanned


def get_startup_time() -> Optional[float]:
    return _startup_time


def get_discovery_sources() -> list:
    return _discovery_sources


def store_discovery_sources(sources: list) -> None:
    global _discovery_sources
    _discovery_sources = sources or []


def get_parser() -> TooldexParser:
    global _parser
    if _parser is None:
        raise RuntimeError(
            "TooldexParser not initialized — call init_parser_from_manifest() at startup"
        )
    return _parser


def init_parser_from_manifest(manifest: TooldexManifest) -> TooldexParser:
    """Install a pre-built manifest into the singleton."""
    global _parser, _last_scanned, _startup_time
    import time
    from datetime import datetime, timezone
    _parser = TooldexParser(manifest)
    _last_scanned = datetime.now(timezone.utc).isoformat()
    if _startup_time is None:
        _startup_time = time.monotonic()
    return _parser
