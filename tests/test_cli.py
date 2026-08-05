"""Unit tests for tooldex/cli.py's `run` command (--json / --no-serve paths only).

The interactive-serve path (uvicorn.run) is never exercised — it blocks forever
by design. All discovery/probing/scanning is mocked so these tests never touch
real MCP clients or the network.
"""
import json as jsonlib
from unittest.mock import patch

from typer.testing import CliRunner

from tooldex import cli as cli_module
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
