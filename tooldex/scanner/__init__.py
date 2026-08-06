"""
tooldex/scanner — security scanning integration using Cisco's mcpscanner library.

YARA (yara_scan.py) runs automatically on every scan. The LLM judge
(llm_judge.py) is opt-in, per-server only, triggered manually — never as
part of the automatic fleet-wide scan.

Env vars:
  TOOLDEX_SECURITY_SCAN              — set to "false" to disable the automatic YARA scan entirely (default: true)
  MCP_SCANNER_CONCURRENCY            — max servers scanned in parallel (default: 8)
  TOOLDEX_LLM_API_KEY                — enables the per-server LLM judge
  TOOLDEX_LLM_MODEL                  — model to use (e.g. gpt-4o, claude-3-5-sonnet)
  TOOLDEX_LLM_RATE_LIMIT_DELAY       — seconds between LLM calls (default: 2.0)
  TOOLDEX_LLM_TEMPERATURE            — sampling temperature (default: 1.0)
  TOOLDEX_LLM_MAX_RETRIES            — max retries on a failed LLM call (default: 6)
  TOOLDEX_LLM_BASE_URL               — custom endpoint (Azure OpenAI, local Ollama/vLLM/LocalAI, etc.)
  TOOLDEX_LLM_API_VERSION            — API version, e.g. for Azure OpenAI
  TOOLDEX_LLM_TIMEOUT                — per-request LLM timeout in seconds (default: 30)

Each also accepts its original mcpscanner name (MCP_SCANNER_LLM_*) as a
fallback — see config._env_with_legacy_fallback.
"""
from tooldex.scanner.yara_scan import scan_servers, active_analyzers, security_scan_enabled
from tooldex.scanner.llm_judge import run_llm_judge_scan, hydrate_llm_cache

__all__ = [
    "scan_servers", "active_analyzers", "security_scan_enabled",
    "run_llm_judge_scan", "hydrate_llm_cache",
]
