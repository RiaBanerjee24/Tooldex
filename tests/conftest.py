"""Shared fixtures for the tooldex test suite."""
import pytest

import tooldex.core.parsers.parser as parser_module


@pytest.fixture(autouse=True)
def reset_parser_singleton():
    """The manifest singleton in core/parsers/parser.py is global, mutable
    process state. Reset it around every test so manifest installs in one
    test can't leak into another.
    """
    def _reset():
        parser_module._parser = None
        parser_module._last_scanned = None
        parser_module._startup_time = None
        parser_module._discovery_sources = []

    _reset()
    yield
    _reset()


@pytest.fixture(autouse=True)
def isolated_llm_cache(tmp_path, monkeypatch):
    """Never touch the user's real ~/.tooldex/llm_scan_cache.json — every
    test gets its own throwaway cache file."""
    from tooldex.scanner import llm_cache
    monkeypatch.setattr(llm_cache, "_CACHE_PATH", tmp_path / "llm_scan_cache.json")


@pytest.fixture(autouse=True)
def reset_llm_jobs():
    """The in-memory LLM-judge job tracker in api/llm_jobs.py is global,
    mutable process state. Reset it around every test."""
    from tooldex.api import llm_jobs
    llm_jobs._llm_jobs.clear()
    yield
    llm_jobs._llm_jobs.clear()


_LLM_ENV_VARS = [
    "TOOLDEX_LLM_API_KEY", "TOOLDEX_LLM_MODEL", "TOOLDEX_LLM_RATE_LIMIT_DELAY",
    "TOOLDEX_LLM_TEMPERATURE", "TOOLDEX_LLM_MAX_RETRIES", "TOOLDEX_LLM_BASE_URL",
    "TOOLDEX_LLM_API_VERSION", "TOOLDEX_LLM_TIMEOUT",
    "MCP_SCANNER_LLM_API_KEY", "MCP_SCANNER_LLM_MODEL", "MCP_SCANNER_LLM_RATE_LIMIT_DELAY",
    "MCP_SCANNER_LLM_TEMPERATURE", "MCP_SCANNER_LLM_MAX_RETRIES", "MCP_SCANNER_LLM_BASE_URL",
    "MCP_SCANNER_LLM_API_VERSION", "MCP_SCANNER_LLM_TIMEOUT",
]


@pytest.fixture(autouse=True)
def isolated_llm_env(monkeypatch):
    """Never let the real shell environment's LLM env vars (or a previous
    test's) leak into a test — every test starts with none of them set.
    Also resets the one-time legacy-fallback warning tracker."""
    from tooldex.scanner import config as scanner_config
    for name in _LLM_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    scanner_config._warned_legacy_llm_vars.clear()
    yield
    scanner_config._warned_legacy_llm_vars.clear()
