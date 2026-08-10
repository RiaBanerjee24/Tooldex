"""
tooldex/cli.py
Tooldex CLI — `run` autodiscovers MCP servers and starts the UI.
"""
import json as _json
import logging
import os
import sys
import uvicorn
import typer
from typing import Optional
from pathlib import Path

from tooldex import __version__
from tooldex._ports import PORT_DEFAULT, find_free_port
from tooldex._spinner import Spinner
from tooldex.preferences import load_prefs, save_pref
from tooldex.core.discovery import detect_all, list_tools_for_all
from tooldex.core.discovery.to_manifest import build_manifest
from tooldex.core.parsers.parser import init_parser_from_manifest, store_discovery_sources
from tooldex.api.app import create_app
from tooldex._cli_output import print_banner, print_summary, result_as_json

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

cli = typer.Typer(
    help="Tooldex — Unified MCP Server Discovery",
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"tooldex {__version__}")
        raise typer.Exit()


@cli.callback()
def callback(
    version: bool = typer.Option(
        None, "--version", "-V",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    pass


@cli.command(context_settings={"help_option_names": ["-h", "--help"]})
def run(
    port: int = typer.Option(
        PORT_DEFAULT, "--port", "-p", "-port",
        help="Starting port. Tooldex increments automatically if the port is occupied (hard limit 49150).",
    ),
    host: str = typer.Option(
        "127.0.0.1", "--host", "-host",
        help="Host/interface to bind the UI server to.",
    ),
    no_serve: bool = typer.Option(
        False, "--no-serve", "-no-serve",
        help="Print the discovery summary and exit without starting the server.",
    ),
    as_json: bool = typer.Option(
        False, "--json", "-json",
        help="Print discovery result as JSON and exit (implies --no-serve, skips probing).",
    ),
    timeout: float = typer.Option(
        10.0, "--timeout", "-timeout",
        help="Per-server probe timeout in seconds.",
    ),
    concurrency: int = typer.Option(
        8, "--concurrency", "-concurrency",
        help="Maximum number of server probes to run concurrently.",
    ),
    no_probe: Optional[list[str]] = typer.Option(
        None, "--no-probe", "-no-probe",
        help=(
            "Skip probing a specific server by name. Repeatable: "
            "--no-probe filesystem --no-probe MCP_DOCKER"
        ),
    ),
    config_paths: Optional[list[Path]] = typer.Option(
        None, "--config", "-config",
        help=(
            "Path to any file to treat as an MCP config ({\"mcpServers\": {...}} format). "
            "Repeatable. Processed before auto-detected locations, so custom configs win "
            "on duplicate server IDs. Parse errors are printed and the file is skipped."
        ),
    ),
    no_cache: bool = typer.Option(
        False, "--no-cache",
        help="Bypass the probe cache and re-probe every server live.",
    ),
    no_security_scan: bool = typer.Option(
        False, "--no-security-scan", "-no-security-scan",
        help=(
            "Skip the automatic YARA security scan (connects to every server a second "
            "time; this disables that second connection entirely). Equivalent to "
            "TOOLDEX_SECURITY_SCAN=false, and also applies to later 'rescan all' calls "
            "for the life of this server."
        ),
    ),
):
    """Autodiscover MCP servers and start the Tooldex UI. Options accept both -- and - prefix."""
    if as_json:
        no_serve = True
    if no_security_scan:
        os.environ["TOOLDEX_SECURITY_SCAN"] = "false"

    # ── permissions: agent CLI status commands ───────────────────────────────
    prefs = load_prefs()
    interactive = sys.stdin.isatty() and not as_json

    def _ask_permission(cli_cmd: str, pref_key: str) -> bool:
        stored = prefs.get(pref_key)
        if stored is True:
            return True
        if not interactive:
            return False
        typer.echo(f"\n  Tooldex wants to run `{cli_cmd}` to show live connection status.\n")
        typer.echo("    1  Yes")
        typer.echo("    2  Yes, for entire session")
        typer.echo("    3  No\n")
        while True:
            choice = typer.prompt("  Choice", default="1").strip()
            if choice == "1":
                typer.echo("")
                return True
            if choice == "2":
                typer.echo("")
                save_pref(pref_key, True)
                return True
            if choice == "3":
                typer.echo("")
                return False
            typer.echo("  Please enter 1, 2, or 3.")

    # In JSON / non-serve mode: skip all live-status CLI calls — scripting
    # mode should be fast and side-effect-free regardless of stored prefs.
    if as_json or no_serve:
        allow_claude_status = allow_codex_status = allow_cursor_status = False
    else:
        allow_claude_status  = _ask_permission("claude mcp list",       "allow_claude_mcp_list")
        allow_codex_status   = _ask_permission("codex mcp list",        "allow_codex_mcp_list")
        allow_cursor_status  = _ask_permission("cursor-agent mcp list", "allow_cursor_mcp_list")

    # ── discovery (quiet, with spinner) ─────────────────────────────────────
    root_logger = logging.getLogger()
    orig_level = root_logger.level
    root_logger.setLevel(logging.WARNING)

    _is_tty = sys.stdout.isatty() and not as_json
    sys.stdout.flush()
    sys.stderr.flush()
    _saved_out = os.dup(1)
    _saved_err = os.dup(2)
    _devnull = os.open(os.devnull, os.O_WRONLY)
    os.dup2(_devnull, 1)
    os.dup2(_devnull, 2)
    os.close(_devnull)

    spinner = Spinner()
    if _is_tty:
        spinner.start()

    try:
        config_result = detect_all(
            custom_paths=config_paths,
            allow_claude_status=allow_claude_status,
            allow_codex_status=allow_codex_status,
            allow_cursor_status=allow_cursor_status,
        )

        tool_results = []
        if not as_json:
            skip_names = set(no_probe or [])
            servers_to_probe = [
                s for s in config_result.servers.values()
                if s.name not in skip_names
            ]
            if servers_to_probe:
                tool_results = list_tools_for_all(
                    servers_to_probe,
                    timeout=timeout,
                    concurrency=concurrency,
                    use_cache=not no_cache,
                )
    finally:
        spinner.stop()
        root_logger.setLevel(orig_level)
        os.dup2(_saved_out, 1)
        os.close(_saved_out)
        os.dup2(_saved_err, 2)
        os.close(_saved_err)

    # ── output ───────────────────────────────────────────────────────────────
    if as_json:
        try:
            payload = _json.dumps(result_as_json(config_result), indent=2, default=str)
        except Exception as exc:
            typer.echo(f"Error serialising JSON: {exc}", err=True)
            raise typer.Exit(1)
        os.write(1, (payload + "\n").encode())
        raise typer.Exit(0)

    from tooldex.scanner import scan_servers, security_scan_enabled
    if security_scan_enabled():
        probed_ids = {r.server_id for r in tool_results if r.ok}
        servers_to_scan = {
            sid: srv
            for sid, srv in config_result.servers.items()
            if sid in probed_ids
        }
        scan_results = scan_servers(servers_to_scan)
    else:
        reason = "--no-security-scan flag was passed" if no_security_scan else "TOOLDEX_SECURITY_SCAN is set to false"
        typer.secho(f"\n  Security scan skipped — {reason}.", fg="yellow")
        scan_results = {}

    print_summary(config_result, tool_results)

    if no_serve:
        raise typer.Exit(0)

    if not config_result.servers:
        typer.echo(
            "\n  No servers discovered — nothing to serve. "
            "Configure an MCP client (Claude Code, Cursor, etc.) "
            "and re-run `tooldex run`.\n",
        )
        raise typer.Exit(0)

    # ── start server ─────────────────────────────────────────────────────────
    actual_port = find_free_port(port, host)
    if actual_port != port:
        typer.echo(f"\n  Port {port} in use — using {actual_port} instead.")

    store_discovery_sources(config_result.sources)
    manifest = build_manifest(config_result, tool_results, scan_results)
    from tooldex.scanner import hydrate_llm_cache
    hydrate_llm_cache(manifest)
    init_parser_from_manifest(manifest)

    total_tools = sum(len(s.discovered_tools) for s in manifest.servers.values())
    url = f"http://{host}:{actual_port}"
    print_banner(len(manifest.servers), total_tools, url)

    uvicorn.run(create_app(), host=host, port=actual_port, log_level="warning")


def main():
    cli()
