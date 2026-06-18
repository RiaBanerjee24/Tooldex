"""
toolpool/cli.py
Toolpool CLI — `run` reads toolpool.yml, `discover` autodiscovers everything.
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

# Ports to always skip: IANA well-known (0-1023) plus common dev/service ports
_SKIP_PORTS: frozenset[int] = frozenset({
    *range(0, 1024),
    3000, 3001,   # React / Node
    3306,         # MySQL
    4200,         # Angular
    5000, 5001,   # Flask / various
    5173,         # Vite dev
    5432,         # PostgreSQL
    6379,         # Redis
    8000, 8001,   # Django / common HTTP alt
    8080, 8081,   # Common HTTP alt
    8443,         # HTTPS alt
    8888,         # Jupyter Notebook
    9000,         # SonarQube / PHP-FPM
    9090,         # Prometheus
    9092,         # Kafka
    9200,         # Elasticsearch
    27017,        # MongoDB
})


def _find_free_port(start: int, host: str) -> int:
    """Return the first non-skipped, non-occupied port >= start."""
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
    typer.echo(
        f"\n  Error: No free port found between {start} and {_PORT_HARD_LIMIT}.\n",
        err=True,
    )
    raise typer.Exit(1)

# Hoisted so tests can patch these as attributes of this module.
# Cost is ~negligible import time since the discovery package doesn't
# touch the network or disk at import time.
from toolpool.core.discovery import detect_all, list_tools_for_all
from toolpool.core.discovery.to_manifest import build_manifest
from toolpool.core.parsers.parser import init_parser, init_parser_from_manifest
from toolpool.api.app import create_app
from toolpool._cli_output import print_summary, result_as_json

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s  %(name)s  %(message)s"
)

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
    """Runs a background thread that prints a seconds counter directly to the tty."""

    def __init__(self):
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._tick, daemon=True)

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

    def stop(self):
        self._stop.set()
        self._thread.join()
        try:
            with open("/dev/tty", "w") as tty:
                tty.write("\r" + " " * 30 + "\r")
                tty.flush()
        except OSError:
            pass

cli = typer.Typer(
    help="Toolpool — AI Agent Permission Observatory",
    no_args_is_help=True,
)


@cli.callback()
def callback():
    pass

def _discover_config() -> Optional[Path]:
    """
    Walk up from cwd looking for toolpool.yml or toolpool.yaml.
    Stops at the filesystem root.
    Returns the first match found, or None.
    """
    current = Path.cwd()
    while True:
        for name in ("toolpool.yml", "toolpool.yaml"):
            candidate = current / name
            if candidate.exists():
                return candidate
        parent = current.parent
        if parent == current:
            # reached filesystem root — nothing found
            return None
        current = parent

@cli.command()
def run(
    config: Optional[str] = typer.Option(
        None, "--config", "-c",
        help=(
            "Path to your toolpool.yml file. "
            "If omitted, toolpool searches upward from the current directory."
        )
    ),
    port: int = typer.Option(
        _PORT_DEFAULT, "--port", "-p",
        help="Starting port. Increments automatically if occupied (hard limit 49150)."
    ),
    host: str = typer.Option(
        "127.0.0.1", "--host",
        help="Host to bind to"
    ),
):
    """Start the Toolpool Observatory server."""
    # ── resolve port ──────────────────────────────────────────────────────────
    actual_port = _find_free_port(port, host)
    if actual_port != port:
        typer.echo(f"\n  Port {port} in use — using {actual_port} instead.")

    # ── resolve config path ───────────────────────────────────────────────────
    if config:
        config_path = Path(config)
        if not config_path.exists():
            typer.echo(
                f"\n  Error: Config file not found: {config}\n",
                err=True
            )
            raise typer.Exit(1)
    else:
        discovered = _discover_config()
        if discovered is None:
            typer.echo(
                "\n  Error: No toolpool.yml found.\n"
                "\n  Toolpool searched upward from the current directory"
                " and found nothing.\n"
                "\n  Either create a toolpool.yml in your project root,"
                " or pass --config <path>.\n",
                err=True
            )
            raise typer.Exit(1)
        config_path = discovered
        typer.echo(f"\n  Found config: {config_path}")
 
    # ── load and validate ─────────────────────────────────────────────────────
    try:
        parser = init_parser(str(config_path))
        manifest = parser.manifest
    except FileNotFoundError as e:
        typer.echo(f"\n  Error: {e}\n", err=True)
        raise typer.Exit(1)
    except ValueError as e:
        typer.echo(f"\n  Config error: {e}\n", err=True)
        raise typer.Exit(1)
 
    # ── surface reference warnings before starting ────────────────────────────
    warnings = parser.validate_references()
    if warnings:
        typer.echo(f"\n  Warnings in {config_path}:")
        for w in warnings:
            typer.echo(f"    ⚠  {w}")
 
    typer.echo(f"""
  ╔══════════════════════════════════════════════════╗
  ║               toolpool  v0.1.0                    ║
  ╠══════════════════════════════════════════════════╣
  ║  Config   {str(config_path):<39}║
  ║  Agents   {len(manifest.agents):<39}║
  ║  Servers  {len(manifest.servers):<39}║
  ╠══════════════════════════════════════════════════╣
  ║  →  http://{host}:{actual_port}                  ║
  ╚══════════════════════════════════════════════════╝
""")

    uvicorn.run(
        create_app(),
        host=host,
        port=actual_port,
        log_level="warning",
    )


# ---------------------------------------------------------------------------
# toolpool discover
# ---------------------------------------------------------------------------

@cli.command()
def discover(
    port: int = typer.Option(
        _PORT_DEFAULT, "--port", "-p",
        help="Starting port. Increments automatically if occupied (hard limit 49150)."
    ),
    host: str = typer.Option("127.0.0.1", "--host", help="Host to bind to"),
    no_serve: bool = typer.Option(
        False, "--no-serve",
        help="Print the discovery summary and exit without starting the server.",
    ),
    as_json: bool = typer.Option(
        False, "--json",
        help="Print discovery result as JSON (implies --no-serve).",
    ),
    timeout: float = typer.Option(
        10.0, "--timeout",
        help="Per-server probe timeout in seconds.",
    ),
    concurrency: int = typer.Option(
        8, "--concurrency",
        help="Max concurrent server probes.",
    ),
    skip_probe: bool = typer.Option(
        False, "--skip-probe",
        help="Only detect servers from configs — do not call tools/list on them.",
    ),
    config_paths: Optional[list[Path]] = typer.Option(
        None, "--config",
        help=(
            "Path to an MCP config file to include. Repeatable — pass "
            "--config multiple times to include several. Processed BEFORE "
            "auto-detected locations, so custom configs win on duplicate "
            "server IDs."
        ),
    ),
    no_auto_detect: bool = typer.Option(
        False, "--no-auto-detect",
        help=(
            "Skip the built-in search of Claude Desktop / Claude Code / "
            "Cursor / Windsurf config locations. Only --config paths are "
            "read. Useful for hermetic test and CI runs."
        ),
    ),
):
    """
    Autodiscover MCP servers and their tools.

    Scans known MCP-client config files (Claude Desktop, Claude Code,
    Cursor, Windsurf) and/or user-provided --config paths, probes each
    discovered stdio server for its tool surface, and either prints a
    summary or starts the Observatory UI.
    """
    # --json implies --no-serve
    if as_json:
        no_serve = True

    # Validate the combination: --no-auto-detect without --config means
    # we'd scan literally nothing, which is almost certainly a mistake.
    if no_auto_detect and not config_paths:
        typer.echo(
            typer.style(
                "\n  Error: --no-auto-detect requires at least one --config path.\n",
                fg="red",
            ),
            err=True,
        )
        raise typer.Exit(2)

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

    allow_claude_status  = _ask_permission("claude mcp list",       "allow_claude_mcp_list")
    allow_codex_status   = _ask_permission("codex mcp list",        "allow_codex_mcp_list")
    allow_cursor_status  = _ask_permission("cursor-agent mcp list", "allow_cursor_mcp_list")

    # ── phases 1 & 2: detect + probe (quiet, with counter) ───────────────────
    root_logger = logging.getLogger()
    orig_level = root_logger.level
    root_logger.setLevel(logging.WARNING)

    _is_tty = sys.stdout.isatty() and not as_json

    # Redirect raw stdout/stderr fds to /dev/null so subprocess noise
    # (Docker MCP gateway, mcp-remote, MCP server startup messages) is
    # silenced. The spinner writes directly to /dev/tty, bypassing these fds.
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
            auto_detect=not no_auto_detect,
            allow_claude_status=allow_claude_status,
            allow_codex_status=allow_codex_status,
            allow_cursor_status=allow_cursor_status,
        )

        tool_results = []
        if not skip_probe and config_result.servers:
            servers = list(config_result.servers.values())
            tool_results = list_tools_for_all(
                servers, timeout=timeout, concurrency=concurrency,
            )
    finally:
        spinner.stop()
        root_logger.setLevel(orig_level)
        # Restore stdout/stderr before printing summary
        os.dup2(_saved_out, 1)
        os.close(_saved_out)
        os.dup2(_saved_err, 2)
        os.close(_saved_err)

    # ── output ───────────────────────────────────────────────────────────────
    if as_json:
        typer.echo(_json.dumps(
            result_as_json(config_result, tool_results),
            indent=2, default=str,
        ))
        raise typer.Exit(0)

    print_summary(config_result, tool_results)

    if no_serve:
        raise typer.Exit(0)

    if not config_result.servers:
        typer.echo(
            "\n  No servers discovered — nothing to serve. "
            "Configure an MCP client (Claude Desktop, Cursor, etc.) "
            "and re-run `toolpool discover`.\n",
        )
        raise typer.Exit(0)

    # ── resolve port ──────────────────────────────────────────────────────────
    actual_port = _find_free_port(port, host)
    if actual_port != port:
        typer.echo(f"\n  Port {port} in use — using {actual_port} instead.")

    # ── install manifest into the parser singleton and start server ──────────
    manifest = build_manifest(config_result, tool_results)
    init_parser_from_manifest(manifest)

    total_tools = sum(len(s.discovered_tools) for s in manifest.servers.values())

    def _row(text: str, width: int = 50) -> str:
        # Pad/truncate to fit inside the box. Em-dash and other wide chars
        # are still 1 grapheme in Python, so len() is fine here.
        if len(text) > width:
            text = text[: width - 1] + "…"
        return f"║{text.ljust(width)}║"

    url = f"http://{host}:{actual_port}"
    typer.echo("\n  " + "╔" + "═" * 50 + "╗")
    typer.echo("  " + _row("       toolpool DISCOVER  v0.1.0"))
    typer.echo("  " + "╠" + "═" * 50 + "╣")
    typer.echo("  " + _row(f"  Servers  {len(manifest.servers)}"))
    typer.echo("  " + _row(f"  Tools    {total_tools}"))
    typer.echo("  " + _row("  Agents   (not yet — Phase 1 AST scan pending)"))
    typer.echo("  " + "╠" + "═" * 50 + "╣")
    typer.echo("  " + _row(f"  →  {url}"))
    typer.echo("  " + "╚" + "═" * 50 + "╝\n")

    uvicorn.run(
        create_app(),
        host=host,
        port=actual_port,
        log_level="warning",
    )


def main():
    cli()