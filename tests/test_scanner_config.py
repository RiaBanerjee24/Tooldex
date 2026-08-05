"""Unit tests for tooldex/scanner/config.py."""
from tooldex.scanner.config import _env_with_legacy_fallback, build_config


class TestEnvWithLegacyFallback:
    def test_new_name_wins_when_both_set(self, monkeypatch):
        monkeypatch.setenv("TOOLDEX_LLM_MODEL", "gpt-4o")
        monkeypatch.setenv("MCP_SCANNER_LLM_MODEL", "gpt-3.5")
        assert _env_with_legacy_fallback("TOOLDEX_LLM_MODEL", "MCP_SCANNER_LLM_MODEL") == "gpt-4o"

    def test_falls_back_to_legacy_when_new_unset(self, monkeypatch):
        monkeypatch.setenv("MCP_SCANNER_LLM_MODEL", "gpt-3.5")
        assert _env_with_legacy_fallback("TOOLDEX_LLM_MODEL", "MCP_SCANNER_LLM_MODEL") == "gpt-3.5"

    def test_none_when_neither_set(self):
        assert _env_with_legacy_fallback("TOOLDEX_LLM_MODEL", "MCP_SCANNER_LLM_MODEL") is None

    def test_warns_once_on_legacy_fallback(self, monkeypatch, capsys):
        monkeypatch.setenv("MCP_SCANNER_LLM_MODEL", "gpt-3.5")
        _env_with_legacy_fallback("TOOLDEX_LLM_MODEL", "MCP_SCANNER_LLM_MODEL")
        _env_with_legacy_fallback("TOOLDEX_LLM_MODEL", "MCP_SCANNER_LLM_MODEL")
        out = capsys.readouterr().out
        # the var name legitimately appears twice within a single notice line
        # ("X is set but ... using X for now") — count notice lines instead
        assert out.count("is set but") == 1
        assert "TOOLDEX_LLM_MODEL" in out

    def test_no_warning_when_new_name_used(self, monkeypatch, capsys):
        monkeypatch.setenv("TOOLDEX_LLM_MODEL", "gpt-4o")
        _env_with_legacy_fallback("TOOLDEX_LLM_MODEL", "MCP_SCANNER_LLM_MODEL")
        assert capsys.readouterr().out == ""

    def test_no_warning_when_neither_set(self, capsys):
        _env_with_legacy_fallback("TOOLDEX_LLM_MODEL", "MCP_SCANNER_LLM_MODEL")
        assert capsys.readouterr().out == ""

    def test_different_var_pairs_warn_independently(self, monkeypatch, capsys):
        monkeypatch.setenv("MCP_SCANNER_LLM_MODEL", "gpt-3.5")
        monkeypatch.setenv("MCP_SCANNER_LLM_TIMEOUT", "60")
        _env_with_legacy_fallback("TOOLDEX_LLM_MODEL", "MCP_SCANNER_LLM_MODEL")
        _env_with_legacy_fallback("TOOLDEX_LLM_TIMEOUT", "MCP_SCANNER_LLM_TIMEOUT")
        out = capsys.readouterr().out
        assert "MCP_SCANNER_LLM_MODEL" in out
        assert "MCP_SCANNER_LLM_TIMEOUT" in out


class TestBuildConfig:
    def test_defaults_when_nothing_set(self, monkeypatch):
        monkeypatch.setenv("TOOLDEX_LLM_API_KEY", "sk-test")
        config = build_config()
        assert config.llm_provider_api_key == "sk-test"
        assert config.llm_rate_limit_delay == 2.0
        assert config.llm_max_retries == 6
        assert config.llm_temperature == 1.0
        assert config.llm_base_url is None
        assert config.llm_api_version is None
        # unset -> we pass None -> mcpscanner's own Config falls back to its
        # own default (30s), it's not left as None
        assert config.llm_timeout == 30

    def test_no_api_key_set_leaves_it_none(self):
        config = build_config()
        assert config.llm_provider_api_key is None

    def test_reads_all_tooldex_vars(self, monkeypatch):
        monkeypatch.setenv("TOOLDEX_LLM_API_KEY", "sk-test")
        monkeypatch.setenv("TOOLDEX_LLM_MODEL", "claude-3-5-sonnet-latest")
        monkeypatch.setenv("TOOLDEX_LLM_RATE_LIMIT_DELAY", "5.5")
        monkeypatch.setenv("TOOLDEX_LLM_TEMPERATURE", "0.2")
        monkeypatch.setenv("TOOLDEX_LLM_MAX_RETRIES", "2")
        monkeypatch.setenv("TOOLDEX_LLM_BASE_URL", "https://example.com/v1")
        monkeypatch.setenv("TOOLDEX_LLM_API_VERSION", "2024-01-01")
        monkeypatch.setenv("TOOLDEX_LLM_TIMEOUT", "45")

        config = build_config()

        assert config.llm_model == "claude-3-5-sonnet-latest"
        assert config.llm_rate_limit_delay == 5.5
        assert config.llm_temperature == 0.2
        assert config.llm_max_retries == 2
        assert config.llm_base_url == "https://example.com/v1"
        assert config.llm_api_version == "2024-01-01"
        assert config.llm_timeout == 45.0

    def test_falls_back_to_legacy_mcp_scanner_vars(self, monkeypatch):
        monkeypatch.setenv("MCP_SCANNER_LLM_API_KEY", "sk-legacy")
        monkeypatch.setenv("MCP_SCANNER_LLM_MODEL", "gpt-4o-legacy")
        config = build_config()
        assert config.llm_provider_api_key == "sk-legacy"
        assert config.llm_model == "gpt-4o-legacy"

    def test_new_name_overrides_legacy_when_both_set(self, monkeypatch):
        monkeypatch.setenv("TOOLDEX_LLM_MODEL", "new-model")
        monkeypatch.setenv("MCP_SCANNER_LLM_MODEL", "old-model")
        config = build_config()
        assert config.llm_model == "new-model"
