"""tooldex/scanner/config.py — builds mcpscanner's Config from TOOLDEX_LLM_* env vars."""
from __future__ import annotations

import os

from mcpscanner import Config

_warned_legacy_llm_vars: set[str] = set()


def _env_with_legacy_fallback(new_name: str, legacy_name: str) -> str | None:
    """
    Read `new_name`, falling back to mcpscanner's original `legacy_name` if
    unset — so an existing mcpscanner-native setup keeps working un-migrated.
    Prints a one-time bright-yellow CLI notice the first time a fallback is
    actually used.
    """
    value = os.getenv(new_name)
    if value is not None:
        return value
    legacy_value = os.getenv(legacy_name)
    if legacy_value is not None and legacy_name not in _warned_legacy_llm_vars:
        _warned_legacy_llm_vars.add(legacy_name)
        print(
            f"\033[93m[tooldex] {legacy_name} is set but {new_name} is not — "
            f"using {legacy_name} for now. Rename it to {new_name}.\033[0m",
            flush=True,
        )
    return legacy_value


def build_config() -> Config:
    rate_limit_delay = float(_env_with_legacy_fallback("TOOLDEX_LLM_RATE_LIMIT_DELAY", "MCP_SCANNER_LLM_RATE_LIMIT_DELAY") or "2.0")
    max_retries = int(_env_with_legacy_fallback("TOOLDEX_LLM_MAX_RETRIES", "MCP_SCANNER_LLM_MAX_RETRIES") or "6")
    temperature = float(_env_with_legacy_fallback("TOOLDEX_LLM_TEMPERATURE", "MCP_SCANNER_LLM_TEMPERATURE") or "1.0")
    timeout = _env_with_legacy_fallback("TOOLDEX_LLM_TIMEOUT", "MCP_SCANNER_LLM_TIMEOUT")
    return Config(
        llm_provider_api_key=_env_with_legacy_fallback("TOOLDEX_LLM_API_KEY", "MCP_SCANNER_LLM_API_KEY"),
        llm_model=_env_with_legacy_fallback("TOOLDEX_LLM_MODEL", "MCP_SCANNER_LLM_MODEL"),
        llm_rate_limit_delay=rate_limit_delay,
        llm_max_retries=max_retries,
        llm_temperature=temperature,
        llm_base_url=_env_with_legacy_fallback("TOOLDEX_LLM_BASE_URL", "MCP_SCANNER_LLM_BASE_URL"),
        llm_api_version=_env_with_legacy_fallback("TOOLDEX_LLM_API_VERSION", "MCP_SCANNER_LLM_API_VERSION"),
        llm_timeout=float(timeout) if timeout else None,
    )
