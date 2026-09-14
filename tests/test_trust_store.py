"""Unit tests for tooldex/core/discovery/trust_store.py."""
import os
import time
from unittest.mock import patch

import pytest

from tooldex.core.discovery import trust_store
from tooldex.core.discovery.results import DiscoveredTool
from tooldex.core.models.server import MCPServer


def _script_server(tmp_path, name="fs", body="print('hi')\n"):
    script = tmp_path / f"{name}.py"
    script.write_text(body)
    return MCPServer(id=f"a:{name}", name=name, command="python3", args=[str(script)], transport="stdio")


@pytest.fixture(autouse=True)
def isolated_trust_store(tmp_path, monkeypatch):
    monkeypatch.setattr(trust_store, "_STORE_PATH", tmp_path / "trust_store.json")


def _server(**overrides):
    defaults = dict(id="a:srv", name="srv", command="npx", args=["-y", "pkg"], transport="stdio")
    defaults.update(overrides)
    return MCPServer(**defaults)


def _tools(*names_and_descs):
    return [
        DiscoveredTool(name=name, server_id="a:srv", description=desc, input_schema={})
        for name, desc in names_and_descs
    ]


class TestGetSetDecision:
    def test_never_decided_returns_none(self):
        assert trust_store.get_decision(_server()) is None

    def test_allow_round_trips(self):
        server = _server()
        trust_store.set_decision(server, "allow")
        assert trust_store.get_decision(server) == "allow"

    def test_deny_round_trips(self):
        server = _server()
        trust_store.set_decision(server, "deny")
        assert trust_store.get_decision(server) == "deny"

    def test_decision_is_pinned_to_exact_invocation(self):
        """Editing command/args after approval must not carry the decision over."""
        approved = _server(args=["-y", "pkg"])
        trust_store.set_decision(approved, "allow")

        edited = _server(args=["-y", "pkg", "--danger"])
        assert trust_store.get_decision(edited) is None

    def test_env_values_do_not_affect_decision_identity(self):
        trust_store.set_decision(_server(env={"API_KEY": "secret1"}), "allow")
        assert trust_store.get_decision(_server(env={"API_KEY": "secret2"})) == "allow"


class TestRemoveDecision:
    def test_revokes_back_to_pending(self):
        server = _server()
        trust_store.set_decision(server, "allow")
        trust_store.remove_decision(server)
        assert trust_store.get_decision(server) is None

    def test_noop_when_nothing_decided(self):
        trust_store.remove_decision(_server())  # must not raise


class TestRecordProbeResult:
    def test_no_decision_on_file_is_a_noop(self):
        server = _server()
        assert trust_store.record_probe_result(server, _tools(("t1", "d1"))) is False

    def test_denied_server_is_a_noop(self):
        server = _server()
        trust_store.set_decision(server, "deny")
        assert trust_store.record_probe_result(server, _tools(("t1", "d1"))) is False

    def test_first_probe_after_approval_baselines_without_flagging_drift(self):
        server = _server()
        trust_store.set_decision(server, "allow")
        assert trust_store.record_probe_result(server, _tools(("t1", "d1"))) is False
        assert trust_store.get_approved_tools(server) == [
            {"name": "t1", "description": "d1", "input_schema": {}}
        ]

    def test_matching_second_probe_reports_no_drift(self):
        server = _server()
        trust_store.set_decision(server, "allow")
        trust_store.record_probe_result(server, _tools(("t1", "d1")))
        assert trust_store.record_probe_result(server, _tools(("t1", "d1"))) is False

    def test_changed_description_is_flagged_as_drift(self):
        server = _server()
        trust_store.set_decision(server, "allow")
        trust_store.record_probe_result(server, _tools(("t1", "d1")))
        assert trust_store.record_probe_result(server, _tools(("t1", "d1-changed"))) is True

    def test_added_tool_is_flagged_as_drift(self):
        server = _server()
        trust_store.set_decision(server, "allow")
        trust_store.record_probe_result(server, _tools(("t1", "d1")))
        assert trust_store.record_probe_result(server, _tools(("t1", "d1"), ("t2", "d2"))) is True

    def test_reapproving_rebaselines_and_clears_drift(self):
        server = _server()
        trust_store.set_decision(server, "allow")
        trust_store.record_probe_result(server, _tools(("t1", "d1")))
        trust_store.record_probe_result(server, _tools(("t1", "d1-changed")))  # now drifted

        trust_store.set_decision(server, "allow")  # re-approve
        assert trust_store.get_approved_tools(server) is None
        assert trust_store.record_probe_result(server, _tools(("t1", "d1-changed"))) is False


class TestLocalScriptPinning:
    def test_editing_approved_script_leaves_decision_allow_but_flags_files_changed(self, tmp_path):
        """get_decision() is deliberately unaffected by file drift now — it's
        a raw read of the stored decision. files_changed_since_approval() is
        the pre-execution signal mcp_client.probe_server actually gates on."""
        server = _script_server(tmp_path)
        trust_store.set_decision(server, "allow")
        assert trust_store.get_decision(server) == "allow"
        assert trust_store.files_changed_since_approval(server) is False

        (tmp_path / "fs.py").write_text("print('modified')\n")

        assert trust_store.get_decision(server) == "allow"
        assert trust_store.files_changed_since_approval(server) is True

    def test_reverting_the_edit_clears_the_flag(self, tmp_path):
        """Not persistent state about "was ever edited" — purely a live
        comparison against disk right now."""
        server = _script_server(tmp_path)
        trust_store.set_decision(server, "allow")
        (tmp_path / "fs.py").write_text("print('modified')\n")
        assert trust_store.files_changed_since_approval(server) is True

        (tmp_path / "fs.py").write_text("print('hi')\n")
        assert trust_store.files_changed_since_approval(server) is False

    def test_unmodified_script_stays_approved(self, tmp_path):
        server = _script_server(tmp_path)
        trust_store.set_decision(server, "allow")
        assert trust_store.get_decision(server) == "allow"

    def test_files_changed_since_approval_flag(self, tmp_path):
        server = _script_server(tmp_path)
        assert trust_store.files_changed_since_approval(server) is False  # never approved
        trust_store.set_decision(server, "allow")
        assert trust_store.files_changed_since_approval(server) is False
        (tmp_path / "fs.py").write_text("print('modified')\n")
        assert trust_store.files_changed_since_approval(server) is True

    def test_denied_server_is_not_reported_as_files_changed(self, tmp_path):
        server = _script_server(tmp_path)
        trust_store.set_decision(server, "deny")
        (tmp_path / "fs.py").write_text("print('modified')\n")
        assert trust_store.files_changed_since_approval(server) is False

    def test_reapproving_edited_script_rebaselines(self, tmp_path):
        server = _script_server(tmp_path)
        trust_store.set_decision(server, "allow")
        (tmp_path / "fs.py").write_text("print('modified')\n")
        assert trust_store.files_changed_since_approval(server) is True

        trust_store.set_decision(server, "allow")  # re-approve the edited version
        assert trust_store.get_decision(server) == "allow"
        assert trust_store.files_changed_since_approval(server) is False

    def test_package_manager_command_has_nothing_to_pin(self):
        """npx/uvx-style commands reference no local file — approval should
        never be affected by file-hash logic for them."""
        server = MCPServer(id="a:pkg", name="pkg", command="npx", args=["-y", "some-package"], transport="stdio")
        trust_store.set_decision(server, "allow")
        assert trust_store.get_decision(server) == "allow"
        assert trust_store.files_changed_since_approval(server) is False

    def test_sibling_module_the_entry_script_imports_is_also_pinned(self, tmp_path):
        """A real MCP server is rarely one file — editing a sibling module
        the entry script imports from must be caught, not just edits to the
        entry script's own bytes."""
        (tmp_path / "tools_impl.py").write_text("def echo_impl(t):\n    return t\n")
        server = _script_server(tmp_path, body="from tools_impl import echo_impl\n")
        trust_store.set_decision(server, "allow")
        assert trust_store.files_changed_since_approval(server) is False

        (tmp_path / "tools_impl.py").write_text("def echo_impl(t):\n    return t + ' [MODIFIED]'\n")
        assert trust_store.files_changed_since_approval(server) is True

    def test_new_sibling_file_added_after_approval_is_caught(self, tmp_path):
        server = _script_server(tmp_path)
        trust_store.set_decision(server, "allow")
        assert trust_store.files_changed_since_approval(server) is False

        (tmp_path / "new_module.py").write_text("x = 1\n")
        assert trust_store.files_changed_since_approval(server) is True

    def test_nested_subpackage_is_pinned(self, tmp_path):
        (tmp_path / "tools").mkdir()
        (tmp_path / "tools" / "file_ops.py").write_text("def read():\n    pass\n")
        server = _script_server(tmp_path, body="from tools.file_ops import read\n")
        trust_store.set_decision(server, "allow")
        assert trust_store.files_changed_since_approval(server) is False

        (tmp_path / "tools" / "file_ops.py").write_text("def read():\n    return 'changed'\n")
        assert trust_store.files_changed_since_approval(server) is True

    def test_vendor_and_vcs_directories_are_not_walked(self, tmp_path):
        (tmp_path / "node_modules" / "somedep").mkdir(parents=True)
        (tmp_path / "node_modules" / "somedep" / "index.py").write_text("noise = 1\n")
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "config.py").write_text("noise = 2\n")  # nonsense extension but proves dir is skipped
        server = _script_server(tmp_path)
        trust_store.set_decision(server, "allow")

        recorded_paths = trust_store._load()[trust_store.server_key(server)]["file_hashes"].keys()
        assert not any("node_modules" in p for p in recorded_paths)
        assert not any(".git" in p for p in recorded_paths)

    def test_unrelated_sibling_directory_edit_does_not_affect_a_different_server(self, tmp_path):
        """Two entry points in different directories shouldn't cross-pollute."""
        (tmp_path / "a").mkdir()
        (tmp_path / "b").mkdir()
        server_a = _script_server(tmp_path / "a", name="a")
        server_b = _script_server(tmp_path / "b", name="b")
        trust_store.set_decision(server_a, "allow")
        trust_store.set_decision(server_b, "allow")

        (tmp_path / "b" / "extra.py").write_text("x = 1\n")

        assert trust_store.files_changed_since_approval(server_a) is False
        assert trust_store.files_changed_since_approval(server_b) is True

    def test_interpreter_binary_is_hashed_but_its_directory_is_not_walked(self, tmp_path):
        """command resolving to a real file (e.g. an absolute interpreter
        path) should still be pinned itself, but its directory isn't the
        server's project — walking it would sweep in unrelated files that
        happen to live next to the interpreter (a venv's bin/, etc.)."""
        fake_venv = tmp_path / "venv" / "bin"
        fake_venv.mkdir(parents=True)
        interpreter = fake_venv / "python3"
        interpreter.write_text("#!/bin/sh\n")
        (fake_venv / "unrelated_helper.py").write_text("noise = 1\n")

        project_dir = tmp_path / "project"
        project_dir.mkdir()
        script = project_dir / "fs.py"
        script.write_text("print('hi')\n")
        server = MCPServer(id="a:fs", name="fs", command=str(interpreter), args=[str(script)], transport="stdio")
        trust_store.set_decision(server, "allow")

        recorded_paths = trust_store._load()[trust_store.server_key(server)]["file_hashes"].keys()
        assert str(interpreter) in recorded_paths  # the interpreter itself is still pinned
        assert not any("unrelated_helper" in p for p in recorded_paths)  # but its directory wasn't walked

    def test_unchanged_file_is_not_reread_on_check(self, tmp_path):
        """The whole point of stat-first: a file whose size/mtime haven't
        moved must be trusted from its recorded hash without touching its
        content again — this is what keeps repeated checks cheap regardless
        of file count or how many servers are approved."""
        server = _script_server(tmp_path)
        trust_store.set_decision(server, "allow")

        with patch.object(trust_store, "_hash_file") as mock_hash:
            assert trust_store.files_changed_since_approval(server) is False
        mock_hash.assert_not_called()

    def test_touch_without_content_change_is_not_a_false_positive(self, tmp_path):
        """Bumping mtime alone (a save that rewrites identical bytes, or a
        bare `touch`) must fall back to a real content comparison rather
        than treating "metadata moved" as "the code changed"."""
        server = _script_server(tmp_path)
        trust_store.set_decision(server, "allow")

        script = tmp_path / "fs.py"
        new_time = time.time() + 5
        os.utime(script, (new_time, new_time))  # bump mtime, content untouched

        assert trust_store.files_changed_since_approval(server) is False

    def test_actual_content_change_is_still_caught_via_fallback_hash(self, tmp_path):
        server = _script_server(tmp_path)
        trust_store.set_decision(server, "allow")
        (tmp_path / "fs.py").write_text("print('modified')\n")
        assert trust_store.files_changed_since_approval(server) is True

    def test_missing_script_after_approval_is_treated_as_changed(self, tmp_path):
        server = _script_server(tmp_path)
        trust_store.set_decision(server, "allow")
        (tmp_path / "fs.py").unlink()
        assert trust_store.get_decision(server) == "allow"
        assert trust_store.files_changed_since_approval(server) is True

    def test_entry_predating_file_hash_pinning_self_heals_on_next_check(self, tmp_path):
        """A stored 'allow' entry with no file_hashes field at all (written
        by an older version of set_decision, before this feature existed)
        must not be treated as "nothing to check" forever — the very next
        files_changed_since_approval() check should re-derive that this
        server *does* run a local script and flag it, since it was never
        actually verified against anything."""
        server = _script_server(tmp_path)
        store = trust_store._load()
        store[trust_store.server_key(server)] = {
            "decision": "allow", "server_name": server.name,
            "approved_tools": None, "decided_at": 0, "updated_at": 0,
            # deliberately no "file_hashes" key
        }
        trust_store._save(store)

        assert trust_store.get_decision(server) == "allow"
        assert trust_store.files_changed_since_approval(server) is True

        trust_store.set_decision(server, "allow")  # re-approve to migrate it
        assert trust_store.files_changed_since_approval(server) is False


class TestDiffTools:
    def test_added_removed_and_changed(self):
        before = [{"name": "a", "description": "x", "input_schema": {}},
                  {"name": "b", "description": "y", "input_schema": {}}]
        after = [{"name": "a", "description": "x-new", "input_schema": {}},
                 {"name": "c", "description": "z", "input_schema": {}}]
        diff = trust_store.diff_tools(before, after)
        by_tool = {d["tool"]: d["change"] for d in diff}
        assert by_tool == {"a": "changed", "b": "removed", "c": "added"}

    def test_identical_snapshots_produce_no_diff(self):
        snap = [{"name": "a", "description": "x", "input_schema": {}}]
        assert trust_store.diff_tools(snap, snap) == []
