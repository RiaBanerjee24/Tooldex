"""tooldex/preferences.py — persistent CLI preferences store (~/.tooldex/preferences.json)."""
import json
from pathlib import Path


def _prefs_path() -> Path:
    return Path.home() / ".tooldex" / "preferences.json"


def load_prefs() -> dict:
    p = _prefs_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def save_pref(key: str, value) -> None:
    p = _prefs_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    prefs = load_prefs()
    prefs[key] = value
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(prefs, indent=2))
    tmp.replace(p)  # atomic rename on POSIX
