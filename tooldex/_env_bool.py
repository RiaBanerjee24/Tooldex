"""tooldex/_env_bool.py — boolean env var parsing, shared by cli.py and scanner/yara_scan.py.

Deliberately dependency-free (no mcpscanner import) so cli.py can check
TOOLDEX_SECURITY_SCAN before the --json fast path without paying for the
heavier scanner package import.
"""
import os

FALSY = ("false", "0", "no", "off")


def env_flag_enabled(name: str, default: bool = True) -> bool:
    """True unless `name` is explicitly set to a falsy value (case-insensitive)."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in FALSY
