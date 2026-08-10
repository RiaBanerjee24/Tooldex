"""Unit tests for tooldex/preferences.py."""
import pytest

from tooldex import preferences


@pytest.fixture(autouse=True)
def isolated_prefs_path(tmp_path, monkeypatch):
    """Never touch the user's real ~/.tooldex/preferences.json."""
    monkeypatch.setattr(preferences, "_prefs_path", lambda: tmp_path / "preferences.json")


class TestLoadPrefs:
    def test_empty_dict_when_file_missing(self):
        assert preferences.load_prefs() == {}

    def test_empty_dict_on_malformed_json(self):
        preferences._prefs_path().write_text("{not valid json")
        assert preferences.load_prefs() == {}


class TestSavePref:
    def test_round_trip(self):
        preferences.save_pref("allow_claude_mcp_list", True)
        assert preferences.load_prefs() == {"allow_claude_mcp_list": True}

    def test_merges_with_existing_keys(self):
        preferences.save_pref("a", 1)
        preferences.save_pref("b", 2)
        assert preferences.load_prefs() == {"a": 1, "b": 2}

    def test_overwrites_same_key(self):
        preferences.save_pref("a", 1)
        preferences.save_pref("a", 2)
        assert preferences.load_prefs() == {"a": 2}

    def test_creates_parent_directory(self, tmp_path):
        nested = tmp_path / "does" / "not" / "exist" / "preferences.json"
        import tooldex.preferences as prefs_module
        original = prefs_module._prefs_path
        prefs_module._prefs_path = lambda: nested
        try:
            preferences.save_pref("a", 1)
            assert nested.exists()
        finally:
            prefs_module._prefs_path = original

    def test_write_is_atomic_no_tmp_file_left_behind(self):
        preferences.save_pref("a", 1)
        path = preferences._prefs_path()
        assert path.exists()
        assert not path.with_suffix(".tmp").exists()
