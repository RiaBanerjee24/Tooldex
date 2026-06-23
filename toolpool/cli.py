"""
toolpool/cli.py
Toolpool CLI — `run` autodiscovers MCP servers and starts the UI.
"""
import json as _json
import logging
import os
import socket
import sys
import threading
import time
import uvicorn
import typer
from typing import Optional
from pathlib import Path

# ---------------------------------------------------------------------------
# Port resolution
# ---------------------------------------------------------------------------

_PORT_DEFAULT = 8282
_PORT_HARD_LIMIT = 49150

_SKIP_PORTS: frozenset[int] = frozenset({
    *range(0, 1024),
    3000, 3001,
    3306,
    4200,
    5000, 5001,
    5173,
    5432,
    6379,
    8000, 8001,
    8080, 8081,
    8443,
    8888,
    9000,
    9090,
    9092,
    9200,
    27017,
})


def _find_free_port(start: int, host: str) -> int:
    port = start
    while port <= _PORT_HARD_LIMIT:
        if port not in _SKIP_PORTS:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    s.bind((host, port))
                    return port
                except OSError:
                    pass
        port += 1
    typer.echo(f"\n  Error: No free port found between {start} and {_PORT_HARD_LIMIT}.\n", err=True)
    raise typer.Exit(1)


from toolpool import __version__
from toolpool.core.discovery import detect_all, list_tools_for_all
from toolpool.core.discovery.to_manifest import build_manifest
from toolpool.core.parsers.parser import init_parser_from_manifest, store_discovery_sources
from toolpool.api.app import create_app
from toolpool._cli_output import print_summary, result_as_json

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")

# ---------------------------------------------------------------------------
# Preferences store  (~/.toolpool/preferences.json)
# ---------------------------------------------------------------------------

def _prefs_path() -> Path:
    return Path.home() / ".toolpool" / "preferences.json"

def _load_prefs() -> dict:
    p = _prefs_path()
    if not p.exists():
        return {}
    try:
        return _json.loads(p.read_text())
    except Exception:
        return {}

def _save_pref(key: str, value) -> None:
    p = _prefs_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    prefs = _load_prefs()
    prefs[key] = value
    p.write_text(_json.dumps(prefs, indent=2))


# ---------------------------------------------------------------------------
# Discovery spinner  ("toolpooling  3s")
# ---------------------------------------------------------------------------

class _Spinner:
    def __init__(self):
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._tick, daemon=True)
        self._started = False

    def _tick(self):
        try:
            tty = open("/dev/tty", "w")
        except OSError:
            return
        start = time.monotonic()
        try:
            while not self._stop.is_set():
                s = int(time.monotonic() - start)
                tty.write(f"\r  toolpooling  {s}s ")
                tty.flush()
                time.sleep(0.25)
        finally:
            tty.close()

    def start(self):
        self._thread.start()
        self._started = True

    def stop(self):
        self._stop.set()
        if self._started:
            self._thread.join()
        try:
            with open("/dev/tty", "w") as tty:
                tty.write("\r" + " " * 30 + "\r")
                tty.flush()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

cli = typer.Typer(
    help="Toolpool — Unified MCP Server Discovery",
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"toolpool {__version__}")
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
        _PORT_DEFAULT, "--port", "-p", "-port",
        help="Starting port. Toolpool increments automatically if the port is occupied (hard limit 49150).",
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
):
    """
    Autodiscover MCP servers and start the Toolpool UI.

    Scans known MCP-client config files (Claude Code, Cursor, Codex, MCP JSON),
    probes each discovered server for its tool surface, and starts the Toolpool UI.

    \b
    Options support both -- and - prefix  (e.g. --json or -json).
    Use --no-probe <name> to skip probing specific servers by name.
    Use --config <file> to include additional MCP config files.
    """
    if as_json:
        no_serve = True

    # ── permissions: agent CLI status commands ───────────────────────────────
    prefs = _load_prefs()
    interactive = sys.stdin.isatty() and not as_json

    def _ask_permission(cli_cmd: str, pref_key: str) -> bool:
        stored = prefs.get(pref_key)
        if stored is True:
            return True
        if not interactive:
            return False
        typer.echo(f"\n  Toolpool wants to run `{cli_cmd}` to show live connection status.\n")
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
                _save_pref(pref_key, True)
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

    spinner = _Spinner()
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
                    servers_to_probe, timeout=timeout, concurrency=concurrency,
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

    print_summary(config_result, tool_results)

    if no_serve:
        raise typer.Exit(0)

    if not config_result.servers:
        typer.echo(
            "\n  No servers discovered — nothing to serve. "
            "Configure an MCP client (Claude Code, Cursor, etc.) "
            "and re-run `toolpool run`.\n",
        )
        raise typer.Exit(0)

    # ── start server ─────────────────────────────────────────────────────────
    actual_port = _find_free_port(port, host)
    if actual_port != port:
        typer.echo(f"\n  Port {port} in use — using {actual_port} instead.")

    store_discovery_sources(config_result.sources)
    manifest = build_manifest(config_result, tool_results)
    init_parser_from_manifest(manifest)

    total_tools = sum(len(s.discovered_tools) for s in manifest.servers.values())
    url = f"http://{host}:{actual_port}"
    from toolpool._cli_output import print_banner
    print_banner(len(manifest.servers), total_tools, url)

    uvicorn.run(create_app(), host=host, port=actual_port, log_level="warning")


def main():
    cli()
