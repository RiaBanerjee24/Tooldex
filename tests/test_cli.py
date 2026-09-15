"""Unit tests for tooldex/cli.py's `run` command (--json / --no-serve paths only).

The interactive-serve path (uvicorn.run) is never exercised — it blocks forever
by design. All discovery/probing/scanning is mocked so these tests never touch
real MCP clients or the network.
"""
import json as jsonlib
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from tooldex import cli as cli_module
from tooldex.core.discovery import trust_store
from tooldex.core.discovery.results import ConfigDetectionResult, ToolDiscoveryResult, ToolDiscoveryStatus
from tooldex.core.models.server import MCPServer

runner = CliRunner()


def _patched(**overrides):
    """Context-manager stack patching every side-effecting call `run` makes."""
    defaults = dict(
        load_prefs=patch.object(cli_module, "load_prefs", return_value={}),
        detect_all=patch.object(cli_module, "detect_all", return_value=ConfigDetectionResult()),
        list_tools_for_all=patch.object(cli_module, "list_tools_for_all", return_value=[]),
        scan_servers=patch("tooldex.scanner.scan_servers", return_value={}),
        hydrate_llm_cache=patch("tooldex.scanner.hydrate_llm_cache"),
        store_discovery_sources=patch.object(cli_module, "store_discovery_sources"),
        init_parser_from_manifest=patch.object(cli_module, "init_parser_from_manifest"),
        uvicorn_run=patch.object(cli_module.uvicorn, "run"),
    )
    defaults.update(overrides)
    return defaults


class TestVersionFlag:
    def test_version_prints_and_exits_cleanly(self):
        result = runner.invoke(cli_module.cli, ["--version"])
        assert result.exit_code == 0
        assert "tooldex" in result.stdout


class TestJsonMode:
    def test_json_mode_skips_probing_and_prints_json(self, capfd):
        patches = _patched()
        with patches["load_prefs"], patches["detect_all"] as mock_detect, \
             patches["list_tools_for_all"] as mock_probe, \
             patches["scan_servers"], patches["hydrate_llm_cache"], \
             patches["store_discovery_sources"], patches["init_parser_from_manifest"], \
             patches["uvicorn_run"] as mock_uvicorn:
            result = runner.invoke(cli_module.cli, ["run", "--json"])

        assert result.exit_code == 0, result.stdout
        mock_detect.assert_called_once()
        mock_probe.assert_not_called()  # --json implies no probing
        mock_uvicorn.assert_not_called()
        # `run` writes the JSON payload via a raw os.write(1, ...), which bypasses
        # CliRunner's sys.stdout capture — read it back via the real fd instead.
        payload = jsonlib.loads(capfd.readouterr().out)
        assert payload["servers"] == {}

    def test_json_mode_includes_discovered_servers(self, capfd):
        config = ConfigDetectionResult(servers={"custom:fs": MCPServer(id="custom:fs", name="fs")})
        patches = _patched(detect_all=patch.object(cli_module, "detect_all", return_value=config))
        with patches["load_prefs"], patches["detect_all"], patches["list_tools_for_all"], \
             patches["scan_servers"], patches["hydrate_llm_cache"], \
             patches["store_discovery_sources"], patches["init_parser_from_manifest"], \
             patches["uvicorn_run"]:
            result = runner.invoke(cli_module.cli, ["run", "--json"])

        assert result.exit_code == 0, result.stdout
        payload = jsonlib.loads(capfd.readouterr().out)
        assert "custom:fs" in payload["servers"]


class TestNoServeMode:
    def test_no_serve_prints_summary_and_never_starts_server(self):
        config = ConfigDetectionResult(servers={"custom:fs": MCPServer(id="custom:fs", name="fs")})
        probe_ok = ToolDiscoveryResult(server_id="custom:fs", status=ToolDiscoveryStatus.FOUND)
        patches = _patched(
            detect_all=patch.object(cli_module, "detect_all", return_value=config),
            list_tools_for_all=patch.object(cli_module, "list_tools_for_all", return_value=[probe_ok]),
        )
        with patches["load_prefs"], patches["detect_all"], patches["list_tools_for_all"] as mock_probe, \
             patches["scan_servers"] as mock_scan, patches["hydrate_llm_cache"], \
             patches["store_discovery_sources"], patches["init_parser_from_manifest"], \
             patches["uvicorn_run"] as mock_uvicorn:
            result = runner.invoke(cli_module.cli, ["run", "--no-serve"])

        assert result.exit_code == 0, result.stdout
        mock_probe.assert_called_once()
        mock_scan.assert_called_once()
        mock_uvicorn.assert_not_called()

    def test_no_servers_discovered_exits_cleanly_without_serving(self):
        patches = _patched()
        with patches["load_prefs"], patches["detect_all"], patches["list_tools_for_all"], \
             patches["scan_servers"], patches["hydrate_llm_cache"], \
             patches["store_discovery_sources"], patches["init_parser_from_manifest"], \
             patches["uvicorn_run"] as mock_uvicorn:
            result = runner.invoke(cli_module.cli, ["run"])

        assert result.exit_code == 0, result.stdout
        assert "No servers discovered" in result.stdout
        mock_uvicorn.assert_not_called()

    def test_no_security_scan_flag_skips_yara_scan_and_reports_reason(self):
        config = ConfigDetectionResult(servers={"custom:fs": MCPServer(id="custom:fs", name="fs")})
        probe_ok = ToolDiscoveryResult(server_id="custom:fs", status=ToolDiscoveryStatus.FOUND)
        patches = _patched(
            detect_all=patch.object(cli_module, "detect_all", return_value=config),
            list_tools_for_all=patch.object(cli_module, "list_tools_for_all", return_value=[probe_ok]),
        )
        with patches["load_prefs"], patches["detect_all"], patches["list_tools_for_all"], \
             patches["scan_servers"] as mock_scan, patches["hydrate_llm_cache"], \
             patches["store_discovery_sources"], patches["init_parser_from_manifest"], \
             patches["uvicorn_run"]:
            result = runner.invoke(cli_module.cli, ["run", "--no-serve", "--no-security-scan"])

        assert result.exit_code == 0, result.stdout
        mock_scan.assert_not_called()
        assert "Security scan skipped" in result.stdout
        assert "flag was passed" in result.stdout

    def test_no_security_scan_single_dash_alias_also_works(self):
        config = ConfigDetectionResult(servers={"custom:fs": MCPServer(id="custom:fs", name="fs")})
        probe_ok = ToolDiscoveryResult(server_id="custom:fs", status=ToolDiscoveryStatus.FOUND)
        patches = _patched(
            detect_all=patch.object(cli_module, "detect_all", return_value=config),
            list_tools_for_all=patch.object(cli_module, "list_tools_for_all", return_value=[probe_ok]),
        )
        with patches["load_prefs"], patches["detect_all"], patches["list_tools_for_all"], \
             patches["scan_servers"] as mock_scan, patches["hydrate_llm_cache"], \
             patches["store_discovery_sources"], patches["init_parser_from_manifest"], \
             patches["uvicorn_run"]:
            result = runner.invoke(cli_module.cli, ["run", "--no-serve", "-no-security-scan"])

        assert result.exit_code == 0, result.stdout
        mock_scan.assert_not_called()

    def test_env_var_disabled_without_flag_reports_env_var_reason(self, monkeypatch):
        monkeypatch.setenv("TOOLDEX_SECURITY_SCAN", "false")
        config = ConfigDetectionResult(servers={"custom:fs": MCPServer(id="custom:fs", name="fs")})
        probe_ok = ToolDiscoveryResult(server_id="custom:fs", status=ToolDiscoveryStatus.FOUND)
        patches = _patched(
            detect_all=patch.object(cli_module, "detect_all", return_value=config),
            list_tools_for_all=patch.object(cli_module, "list_tools_for_all", return_value=[probe_ok]),
        )
        with patches["load_prefs"], patches["detect_all"], patches["list_tools_for_all"], \
             patches["scan_servers"] as mock_scan, patches["hydrate_llm_cache"], \
             patches["store_discovery_sources"], patches["init_parser_from_manifest"], \
             patches["uvicorn_run"]:
            result = runner.invoke(cli_module.cli, ["run", "--no-serve"])

        assert result.exit_code == 0, result.stdout
        mock_scan.assert_not_called()
        assert "Security scan skipped" in result.stdout
        assert "TOOLDEX_SECURITY_SCAN is set to false" in result.stdout

    def test_env_var_true_and_flag_not_passed_runs_scan(self, monkeypatch):
        monkeypatch.setenv("TOOLDEX_SECURITY_SCAN", "true")
        config = ConfigDetectionResult(servers={"custom:fs": MCPServer(id="custom:fs", name="fs")})
        probe_ok = ToolDiscoveryResult(server_id="custom:fs", status=ToolDiscoveryStatus.FOUND)
        patches = _patched(
            detect_all=patch.object(cli_module, "detect_all", return_value=config),
            list_tools_for_all=patch.object(cli_module, "list_tools_for_all", return_value=[probe_ok]),
        )
        with patches["load_prefs"], patches["detect_all"], patches["list_tools_for_all"], \
             patches["scan_servers"] as mock_scan, patches["hydrate_llm_cache"], \
             patches["store_discovery_sources"], patches["init_parser_from_manifest"], \
             patches["uvicorn_run"]:
            result = runner.invoke(cli_module.cli, ["run", "--no-serve"])

        assert result.exit_code == 0, result.stdout
        mock_scan.assert_called_once()
        assert "Security scan skipped" not in result.stdout

    def test_env_var_true_but_flag_passed_skips_scan(self, monkeypatch):
        monkeypatch.setenv("TOOLDEX_SECURITY_SCAN", "true")
        config = ConfigDetectionResult(servers={"custom:fs": MCPServer(id="custom:fs", name="fs")})
        probe_ok = ToolDiscoveryResult(server_id="custom:fs", status=ToolDiscoveryStatus.FOUND)
        patches = _patched(
            detect_all=patch.object(cli_module, "detect_all", return_value=config),
            list_tools_for_all=patch.object(cli_module, "list_tools_for_all", return_value=[probe_ok]),
        )
        with patches["load_prefs"], patches["detect_all"], patches["list_tools_for_all"], \
             patches["scan_servers"] as mock_scan, patches["hydrate_llm_cache"], \
             patches["store_discovery_sources"], patches["init_parser_from_manifest"], \
             patches["uvicorn_run"]:
            result = runner.invoke(cli_module.cli, ["run", "--no-serve", "--no-security-scan"])

        assert result.exit_code == 0, result.stdout
        mock_scan.assert_not_called()
        assert "flag was passed" in result.stdout

    def test_no_probe_skips_named_servers(self):
        config = ConfigDetectionResult(servers={
            "custom:fs": MCPServer(id="custom:fs", name="fs"),
            "custom:gh": MCPServer(id="custom:gh", name="gh"),
        })
        patches = _patched(detect_all=patch.object(cli_module, "detect_all", return_value=config))
        with patches["load_prefs"], patches["detect_all"], \
             patches["list_tools_for_all"] as mock_probe, \
             patches["scan_servers"], patches["hydrate_llm_cache"], \
             patches["store_discovery_sources"], patches["init_parser_from_manifest"], \
             patches["uvicorn_run"]:
            runner.invoke(cli_module.cli, ["run", "--no-serve", "--no-probe", "fs"])

        probed = mock_probe.call_args[0][0]
        assert [s.name for s in probed] == ["gh"]


class TestTrustGateCli:
    @pytest.fixture(autouse=True)
    def isolated_trust_store(self, tmp_path, monkeypatch):
        monkeypatch.setattr(trust_store, "_STORE_PATH", tmp_path / "trust_store.json")

    def test_trust_all_stdio_approves_pending_servers_before_probing(self):
        server = MCPServer(id="custom:fs", name="fs", command="npx", args=["-y", "pkg"], transport="stdio")
        config = ConfigDetectionResult(servers={"custom:fs": server})
        patches = _patched(detect_all=patch.object(cli_module, "detect_all", return_value=config))
        with patches["load_prefs"], patches["detect_all"], \
             patches["list_tools_for_all"] as mock_probe, \
             patches["scan_servers"], patches["hydrate_llm_cache"], \
             patches["store_discovery_sources"], patches["init_parser_from_manifest"], \
             patches["uvicorn_run"]:
            result = runner.invoke(cli_module.cli, ["run", "--no-serve", "--trust-all-stdio"])

        assert result.exit_code == 0, result.stdout
        assert trust_store.get_decision(server) == "allow"
        mock_probe.assert_called_once()

    def test_trust_all_stdio_does_not_prompt_and_is_noninteractive_safe(self):
        # CliRunner's stdin isn't a tty, so `interactive` is already False here —
        # this just confirms --trust-all-stdio doesn't depend on that at all.
        server = MCPServer(id="custom:fs", name="fs", command="npx", transport="stdio")
        config = ConfigDetectionResult(servers={"custom:fs": server})
        patches = _patched(detect_all=patch.object(cli_module, "detect_all", return_value=config))
        with patches["load_prefs"], patches["detect_all"], patches["list_tools_for_all"], \
             patches["scan_servers"], patches["hydrate_llm_cache"], \
             patches["store_discovery_sources"], patches["init_parser_from_manifest"], \
             patches["uvicorn_run"]:
            result = runner.invoke(cli_module.cli, ["run", "--no-serve", "--trust-all-stdio"])

        assert result.exit_code == 0, result.stdout

    def test_reset_trust_clears_prior_decision_for_named_server(self):
        server = MCPServer(id="custom:fs", name="fs", command="npx", transport="stdio")
        trust_store.set_decision(server, "deny")
        config = ConfigDetectionResult(servers={"custom:fs": server})
        patches = _patched(detect_all=patch.object(cli_module, "detect_all", return_value=config))
        with patches["load_prefs"], patches["detect_all"], patches["list_tools_for_all"], \
             patches["scan_servers"], patches["hydrate_llm_cache"], \
             patches["store_discovery_sources"], patches["init_parser_from_manifest"], \
             patches["uvicorn_run"]:
            result = runner.invoke(cli_module.cli, ["run", "--no-serve", "--reset-trust", "fs"])

        assert result.exit_code == 0, result.stdout
        assert trust_store.get_decision(server) is None

    def test_pending_stdio_server_not_probed_without_trust_all_flag(self):
        # Non-interactive (CliRunner stdin isn't a tty) and no --trust-all-stdio:
        # the real list_tools_for_all/probe_server would fail this server closed.
        # Here list_tools_for_all is mocked, so this just proves nothing in `run`
        # auto-approves a pending server on its own.
        server = MCPServer(id="custom:fs", name="fs", command="npx", transport="stdio")
        config = ConfigDetectionResult(servers={"custom:fs": server})
        patches = _patched(detect_all=patch.object(cli_module, "detect_all", return_value=config))
        with patches["load_prefs"], patches["detect_all"], patches["list_tools_for_all"], \
             patches["scan_servers"], patches["hydrate_llm_cache"], \
             patches["store_discovery_sources"], patches["init_parser_from_manifest"], \
             patches["uvicorn_run"]:
            runner.invoke(cli_module.cli, ["run", "--no-serve"])

        assert trust_store.get_decision(server) is None


class TestResolveStdioTrust:
    """Direct unit tests for cli._resolve_stdio_trust's prompt-batching logic.

    Simulating a real interactive terminal through CliRunner is unreliable
    (sys.stdin.isatty() is False under Click's isolation regardless of
    patching), so this exercises the function directly instead, patching
    typer.prompt for canned input.
    """

    @pytest.fixture(autouse=True)
    def isolated_trust_store(self, tmp_path, monkeypatch):
        monkeypatch.setattr(trust_store, "_STORE_PATH", tmp_path / "trust_store.json")

    def _server(self, name, **overrides):
        defaults = dict(id=f"custom:{name}", name=name, command="npx", args=["-y", name], transport="stdio")
        defaults.update(overrides)
        return MCPServer(**defaults)

    def test_no_pending_servers_never_prompts(self, monkeypatch):
        s = self._server("fs")
        trust_store.set_decision(s, "allow")
        mock_prompt = patch.object(cli_module.typer, "prompt")
        with mock_prompt as prompt_fn:
            cli_module._resolve_stdio_trust([s])
        prompt_fn.assert_not_called()

    def test_choice_1_approves_only_that_server(self):
        s1, s2 = self._server("one"), self._server("two")
        with patch.object(cli_module.typer, "prompt", return_value="1"):
            cli_module._resolve_stdio_trust([s1, s2])
        assert trust_store.get_decision(s1) == "allow"
        assert trust_store.get_decision(s2) == "allow"

    def test_choice_3_denies_only_that_server(self):
        s1 = self._server("one")
        with patch.object(cli_module.typer, "prompt", return_value="3"):
            cli_module._resolve_stdio_trust([s1])
        assert trust_store.get_decision(s1) == "deny"

    def test_choice_2_batches_allow_for_remaining_pending_without_reprompting(self):
        s1, s2, s3 = self._server("one"), self._server("two"), self._server("three")
        with patch.object(cli_module.typer, "prompt", return_value="2") as prompt_fn:
            cli_module._resolve_stdio_trust([s1, s2, s3])
        prompt_fn.assert_called_once()
        assert trust_store.get_decision(s1) == "allow"
        assert trust_store.get_decision(s2) == "allow"
        assert trust_store.get_decision(s3) == "allow"

    def test_invalid_choice_reprompts_until_valid(self):
        s1 = self._server("one")
        with patch.object(cli_module.typer, "prompt", side_effect=["bogus", "1"]) as prompt_fn:
            cli_module._resolve_stdio_trust([s1])
        assert prompt_fn.call_count == 2
        assert trust_store.get_decision(s1) == "allow"

    def test_choice_4_no_longer_exists(self):
        """Only 3 options now: Yes / Yes-for-all-stdio-servers / No — an
        input of "4" must keep reprompting like any other invalid choice."""
        s1 = self._server("one")
        with patch.object(cli_module.typer, "prompt", side_effect=["4", "3"]) as prompt_fn:
            cli_module._resolve_stdio_trust([s1])
        assert prompt_fn.call_count == 2
        assert trust_store.get_decision(s1) == "deny"

    def test_file_changed_since_approval_is_never_reprompted_here(self, tmp_path):
        """A server that's approved but whose script has since changed is
        NOT pending (get_decision still returns "allow") — it's handled
        entirely by mcp_client.probe_server (serve stale tools, flag
        "changed"), never by re-entering this interactive prompt loop."""
        script = tmp_path / "fs.py"
        script.write_text("print('hi')\n")
        s = MCPServer(id="a:fs", name="fs", command="python3", args=[str(script)], transport="stdio")
        trust_store.set_decision(s, "allow")
        script.write_text("print('modified')\n")
        assert trust_store.files_changed_since_approval(s) is True

        with patch.object(cli_module.typer, "prompt") as prompt_fn:
            cli_module._resolve_stdio_trust([s])

        prompt_fn.assert_not_called()
        assert trust_store.get_decision(s) == "allow"

    def test_already_decided_servers_are_skipped(self):
        s1 = self._server("one")
        trust_store.set_decision(s1, "allow")
        with patch.object(cli_module.typer, "prompt") as prompt_fn:
            cli_module._resolve_stdio_trust([s1])
        prompt_fn.assert_not_called()
