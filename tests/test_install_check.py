"""Unit tests for tooldex/_install_check.py."""
import json
from unittest.mock import patch

import pytest

from tooldex import _install_check
from tooldex.core.discovery import trust_store
from tooldex.core.models.server import MCPServer


@pytest.fixture(autouse=True)
def isolated_marker(tmp_path, monkeypatch):
    monkeypatch.setattr(_install_check, "_MARKER_PATH", tmp_path / "install_marker.json")


def _server():
    return MCPServer(id="a:srv", name="srv", command="npx", args=["-y", "pkg"], transport="stdio")


class TestClearTrustOnReinstall:
    def test_first_ever_run_records_baseline_without_wiping(self):
        trust_store.set_decision(_server(), "allow")
        with patch.object(_install_check, "_install_fingerprint", return_value=123.0):
            _install_check.clear_trust_on_reinstall()

        assert trust_store.get_decision(_server()) == "allow"  # nothing to compare against yet — untouched
        assert json.loads(_install_check._MARKER_PATH.read_text())["install_mtime"] == 123.0

    def test_matching_fingerprint_does_not_wipe(self):
        with patch.object(_install_check, "_install_fingerprint", return_value=123.0):
            _install_check.clear_trust_on_reinstall()  # establishes baseline
        trust_store.set_decision(_server(), "allow")

        with patch.object(_install_check, "_install_fingerprint", return_value=123.0):
            _install_check.clear_trust_on_reinstall()

        assert trust_store.get_decision(_server()) == "allow"

    def test_changed_fingerprint_wipes_trust_store(self):
        with patch.object(_install_check, "_install_fingerprint", return_value=123.0):
            _install_check.clear_trust_on_reinstall()  # establishes baseline
        trust_store.set_decision(_server(), "allow")
        assert trust_store.get_decision(_server()) == "allow"

        with patch.object(_install_check, "_install_fingerprint", return_value=456.0):
            _install_check.clear_trust_on_reinstall()

        assert trust_store.get_decision(_server()) is None

    def test_unreadable_fingerprint_is_a_noop(self):
        with patch.object(_install_check, "_install_fingerprint", return_value=None):
            _install_check.clear_trust_on_reinstall()  # must not raise
        assert not _install_check._MARKER_PATH.exists()
