"""
tooldex/_install_check.py

Detects a fresh install (including a reinstall of the same version) and
wipes the trust store when one is found.

Trust decisions live in ~/.tooldex/, outside the installed package, so they
normally survive a `pip uninstall` + reinstall — which is wrong for
security-relevant state: someone who deliberately uninstalled and
reinstalled Tooldex should get a clean slate, not silently inherit every
approval they made under a previous install.

There's no portable install/uninstall hook across pip/pipx/uv, so this uses
a practical proxy instead: pip-family installers write package files fresh
on every install (even reinstalling an identical version), which bumps
their mtime. Comparing the installed package's own mtime against the last
value we recorded catches that. It's a heuristic, not a cryptographic
guarantee — an installer that preserves original build timestamps would
defeat it — but it covers the default behavior of pip/pipx/uv.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("tooldex.install_check")

_MARKER_PATH = Path.home() / ".tooldex" / "install_marker.json"


def _install_fingerprint() -> Optional[float]:
    try:
        import tooldex
        return Path(tooldex.__file__).stat().st_mtime
    except OSError:
        return None


def clear_trust_on_reinstall() -> None:
    """
    Compare this run's install fingerprint against the last recorded one.
    On a mismatch (including "never recorded before"), only wipes the trust
    store if a previous fingerprint actually existed — a first-ever run has
    nothing to distrust yet, it just establishes the baseline.
    """
    current = _install_fingerprint()
    if current is None:
        return

    recorded = None
    if _MARKER_PATH.exists():
        try:
            recorded = json.loads(_MARKER_PATH.read_text()).get("install_mtime")
        except Exception:
            recorded = None

    if recorded is not None and recorded != current:
        from tooldex.core.discovery import trust_store
        trust_store.clear_all()
        logger.info("Detected a fresh Tooldex install — cleared prior trust decisions.")

    try:
        _MARKER_PATH.parent.mkdir(parents=True, exist_ok=True)
        _MARKER_PATH.write_text(json.dumps({"install_mtime": current}))
    except OSError as exc:
        logger.debug("Could not record install marker: %s", exc)
