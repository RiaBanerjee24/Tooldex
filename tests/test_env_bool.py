"""Unit tests for tooldex/_env_bool.py."""
import pytest

from tooldex._env_bool import env_flag_enabled


class TestEnvFlagEnabled:
    def test_default_true_when_unset(self, monkeypatch):
        monkeypatch.delenv("TOOLDEX_TEST_FLAG", raising=False)
        assert env_flag_enabled("TOOLDEX_TEST_FLAG") is True

    def test_respects_explicit_default(self, monkeypatch):
        monkeypatch.delenv("TOOLDEX_TEST_FLAG", raising=False)
        assert env_flag_enabled("TOOLDEX_TEST_FLAG", default=False) is False

    @pytest.mark.parametrize("value", ["false", "False", "FALSE", "0", "no", "off"])
    def test_falsy_values_disable(self, monkeypatch, value):
        monkeypatch.setenv("TOOLDEX_TEST_FLAG", value)
        assert env_flag_enabled("TOOLDEX_TEST_FLAG") is False

    @pytest.mark.parametrize("value", ["true", "1", "yes", "on", "anything-else"])
    def test_other_values_enable(self, monkeypatch, value):
        monkeypatch.setenv("TOOLDEX_TEST_FLAG", value)
        assert env_flag_enabled("TOOLDEX_TEST_FLAG") is True

    def test_whitespace_is_stripped(self, monkeypatch):
        monkeypatch.setenv("TOOLDEX_TEST_FLAG", "  false  ")
        assert env_flag_enabled("TOOLDEX_TEST_FLAG") is False
