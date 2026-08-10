"""tooldex/api/redact.py — strips secrets from server payloads before they leave the API."""
import re
from pathlib import Path

_SENSITIVE_HEADERS = frozenset({"authorization", "x-api-key", "x-auth-token", "x-secret"})
_SENSITIVE_ENV_SEGMENTS = frozenset({"key", "secret", "token", "password", "apikey"})


def _is_sensitive_env(name: str) -> bool:
    parts = re.split(r"[_\-]", name.lower())
    return any(p in _SENSITIVE_ENV_SEGMENTS for p in parts)


def friendly_path(source_path) -> str | None:
    """Return a ~-prefixed path rather than exposing the raw absolute path."""
    if not source_path:
        return None
    try:
        return "~" + str(Path(source_path).relative_to(Path.home()))
    except ValueError:
        return source_path


def redact_server(d: dict) -> dict:
    """Replace values of sensitive HTTP headers and env vars with '***'."""
    result = dict(d)
    if result.get("headers"):
        result["headers"] = {
            k: "***" if k.lower() in _SENSITIVE_HEADERS else v
            for k, v in result["headers"].items()
        }
    if result.get("env"):
        result["env"] = {
            k: "***" if _is_sensitive_env(k) else v
            for k, v in result["env"].items()
        }
    return result
