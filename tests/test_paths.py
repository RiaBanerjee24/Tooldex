"""Unit tests for tooldex/core/discovery/_paths.py."""
from pathlib import Path

import pytest

from tooldex.core.discovery._paths import (
    build_plan,
    claude_code_project_path,
    codex_project_path,
    cursor_project_path,
    mcp_json_project_path,
    walk_up_for,
)


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    return home


class TestWalkUpFor:
    def test_finds_file_in_start_dir(self, fake_home):
        project = fake_home / "project"
        project.mkdir()
        target = project / ".mcp.json"
        target.write_text("{}")
        assert walk_up_for(project, (".mcp.json",)) == target

    def test_finds_file_in_ancestor_dir(self, fake_home):
        project = fake_home / "project"
        nested = project / "src" / "deep"
        nested.mkdir(parents=True)
        target = project / ".mcp.json"
        target.write_text("{}")
        assert walk_up_for(nested, (".mcp.json",)) == target

    def test_returns_none_when_not_found(self, fake_home):
        project = fake_home / "project"
        project.mkdir()
        assert walk_up_for(project, (".mcp.json",)) is None

    def test_stops_at_home_directory(self, fake_home):
        # A file sitting at $HOME should NOT be picked up by a project walk-up.
        (fake_home / ".mcp.json").write_text("{}")
        project = fake_home / "project"
        project.mkdir()
        assert walk_up_for(project, (".mcp.json",)) is None

    def test_multi_part_path(self, fake_home):
        project = fake_home / "project"
        claude_dir = project / ".claude"
        claude_dir.mkdir(parents=True)
        target = claude_dir / "mcp.json"
        target.write_text("{}")
        assert walk_up_for(project, (".claude", "mcp.json")) == target


class TestProjectPathResolvers:
    def test_claude_code_prefers_dot_claude_dir(self, fake_home):
        project = fake_home / "project"
        claude_dir = project / ".claude"
        claude_dir.mkdir(parents=True)
        (claude_dir / "mcp.json").write_text("{}")
        (project / ".claude.json").write_text("{}")
        assert claude_code_project_path(project) == claude_dir / "mcp.json"

    def test_claude_code_falls_back_to_flat_file(self, fake_home):
        project = fake_home / "project"
        project.mkdir()
        flat = project / ".claude.json"
        flat.write_text("{}")
        assert claude_code_project_path(project) == flat

    def test_claude_code_none_when_neither_exists(self, fake_home):
        project = fake_home / "project"
        project.mkdir()
        assert claude_code_project_path(project) is None

    def test_cursor_project_path(self, fake_home):
        project = fake_home / "project"
        cursor_dir = project / ".cursor"
        cursor_dir.mkdir(parents=True)
        (cursor_dir / "mcp.json").write_text("{}")
        assert cursor_project_path(project) == cursor_dir / "mcp.json"

    def test_codex_project_path(self, fake_home):
        project = fake_home / "project"
        codex_dir = project / ".codex"
        codex_dir.mkdir(parents=True)
        (codex_dir / "config.toml").write_text("")
        assert codex_project_path(project) == codex_dir / "config.toml"

    def test_mcp_json_project_path(self, fake_home):
        project = fake_home / "project"
        project.mkdir()
        (project / ".mcp.json").write_text("{}")
        assert mcp_json_project_path(project) == project / ".mcp.json"


class TestBuildPlan:
    def test_returns_expected_client_ids(self, fake_home):
        project = fake_home / "project"
        project.mkdir()
        plan = build_plan(project)
        client_ids = [c for c, _ in plan]
        assert client_ids == [
            "claude_code_project",
            "cursor_project",
            "cursor_user",
            "mcp_json_project",
            "mcp_json_user",
        ]

    def test_resolvers_are_callable(self, fake_home):
        project = fake_home / "project"
        project.mkdir()
        for _, resolver in build_plan(project):
            # Should not raise even when nothing exists.
            resolver()
