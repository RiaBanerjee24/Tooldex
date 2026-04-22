"""
pericat/cli.py
Pericat CLI — `run` reads pericat.yml, `discover` autodiscovers everything.
"""
import json as _json
import logging
import uvicorn
import typer
from typing import Optional
from pathlib import Path

# Hoisted so tests can patch these as attributes of this module.
# Cost is ~negligible import time since the discovery package doesn't
# touch the network or disk at import time.
from pericat.core.discovery import detect_all, list_tools_for_all
from pericat.core.discovery.to_manifest import build_manifest
from pericat.core.parsers.parser import init_parser, init_parser_from_manifest
from pericat.api.app import create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s  %(name)s  %(message)s"
)

cli = typer.Typer(
    help="Pericat — AI Agent Permission Observatory",
    no_args_is_help=True,
)


@cli.callback()
def callback():
    pass

def _discover_config() -> Optional[Path]:
    """
    Walk up from cwd looking for pericat.yml or pericat.yaml.
    Stops at the filesystem root.
    Returns the first match found, or None.
    """
    current = Path.cwd()
    while True:
        for name in ("pericat.yml", "pericat.yaml"):
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
            "Path to your pericat.yml file. "
            "If omitted, Pericat searches upward from the current directory."
        )
    ),
    port: int = typer.Option(
        8282, "--port", "-p",
        help="Port to run on"
    ),
    host: str = typer.Option(
        "127.0.0.1", "--host",
        help="Host to bind to"
    ),
):
    """Start the Pericat Observatory server."""
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
                "\n  Error: No pericat.yml found.\n"
                "\n  Pericat searched upward from the current directory"
                " and found nothing.\n"
                "\n  Either create a pericat.yml in your project root,"
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
  ║               PERICAT  v0.1.0                    ║
  ╠══════════════════════════════════════════════════╣
  ║  Config   {str(config_path):<39}║
  ║  Agents   {len(manifest.agents):<39}║
  ║  Servers  {len(manifest.servers):<39}║
  ╠══════════════════════════════════════════════════╣
  ║  →  http://{host}:{port}                         ║
  ╚══════════════════════════════════════════════════╝
""")
 
    uvicorn.run(
        create_app(),
        host=host,
        port=port,
        log_level="warning",
    )


# ---------------------------------------------------------------------------
# pericat discover
# ---------------------------------------------------------------------------

@cli.command()
def discover(
    port: int = typer.Option(8282, "--port", "-p", help="Port to run on"),
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

    # ── phase 1: config detection ────────────────────────────────────────────
    config_result = detect_all(
        custom_paths=config_paths,
        auto_detect=not no_auto_detect,
    )

    # ── phase 2: probe each discovered server for its tools ──────────────────
    tool_results = []
    if not skip_probe and config_result.servers:
        servers = list(config_result.servers.values())
        tool_results = list_tools_for_all(
            servers, timeout=timeout, concurrency=concurrency,
        )

    # ── output ───────────────────────────────────────────────────────────────
    if as_json:
        typer.echo(_json.dumps(
            _result_as_json(config_result, tool_results),
            indent=2, default=str,
        ))
        raise typer.Exit(0)

    _print_summary(config_result, tool_results)

    if no_serve:
        raise typer.Exit(0)

    if not config_result.servers:
        typer.echo(
            "\n  No servers discovered — nothing to serve. "
            "Configure an MCP client (Claude Desktop, Cursor, etc.) "
            "and re-run `pericat discover`.\n",
        )
        raise typer.Exit(0)

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

    url = f"http://{host}:{port}"
    typer.echo("\n  " + "╔" + "═" * 50 + "╗")
    typer.echo("  " + _row("       PERICAT DISCOVER  v0.1.0"))
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
        port=port,
        log_level="warning",
    )


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _print_summary(config_result, tool_results):
    """Pretty-print discovery to stdout. Separate from JSON output."""
    typer.echo("")
    typer.echo(typer.style("Config files", bold=True))
    for src in config_result.sources:
        symbol, color = _status_symbol(src.status.value)
        client = src.client.ljust(22)
        summary = _source_line_summary(src)
        typer.echo(
            f"  {typer.style(symbol, fg=color)}  {client} {summary}"
        )
        if src.error:
            typer.echo(f"     └─ {typer.style(src.error, fg='red', dim=True)}")

    if config_result.duplicates:
        typer.echo("")
        typer.echo(typer.style("Duplicates (first sighting wins)", bold=True))
        for dup in config_result.duplicates:
            typer.echo(f"  ⚠  {dup}")

    typer.echo("")
    typer.echo(typer.style("Servers & tools", bold=True))
    if not config_result.servers:
        typer.echo("  (none discovered)")
    else:
        tools_by_server = {r.server_id: r for r in tool_results}
        for server_id, server in config_result.servers.items():
            result = tools_by_server.get(server_id)
            if result is None:
                typer.echo(f"  •  {server_id}  (probe skipped)")
                continue
            symbol, color = _status_symbol(result.status.value)
            if result.ok:
                dur = f"{result.duration_ms}ms" if result.duration_ms else ""
                typer.echo(
                    f"  {typer.style(symbol, fg=color)}  "
                    f"{server_id:<22} {len(result.tools)} tools "
                    f"{typer.style(dur, dim=True)}"
                )
                for tool in result.tools:
                    desc = (tool.description or "").split("\n")[0][:60]
                    typer.echo(f"       · {tool.name}  "
                               f"{typer.style(desc, dim=True)}")
            else:
                typer.echo(
                    f"  {typer.style(symbol, fg=color)}  "
                    f"{server_id:<22} {result.status.value}"
                )
                if result.error:
                    typer.echo(f"     └─ {typer.style(result.error, fg='red', dim=True)}")

    # bottom line
    checked = config_result.checked
    servers = len(config_result.servers)
    found_tools = sum(
        len(r.tools) for r in tool_results if r.ok
    )
    typer.echo("")
    typer.echo(typer.style(
        f"Checked {checked} config locations · "
        f"{servers} servers · "
        f"{found_tools} tools",
        bold=True,
    ))


def _status_symbol(status: str) -> tuple[str, str]:
    good = {"found": ("✓", "green"), "empty": ("·", "yellow")}
    if status in good:
        return good[status]
    if status == "not_found":
        return ("✗", "white")
    return ("✗", "red")


def _source_line_summary(src) -> str:
    if src.status.value == "found":
        return f"{len(src.servers)} servers  " + typer.style(
            src.path, dim=True,
        )
    if src.status.value == "not_found":
        return typer.style(f"{src.path}  (not found)", dim=True)
    if src.status.value == "empty":
        return typer.style(f"{src.path}  (no mcpServers)", dim=True)
    return typer.style(f"{src.path}  ({src.status.value})", fg="red", dim=True)


def _result_as_json(config_result, tool_results) -> dict:
    """Machine-readable form for CI / scripts."""
    return {
        "sources": [
            {
                "client": s.client,
                "path": s.path,
                "status": s.status.value,
                "error": s.error,
                "server_ids": [srv.id for srv in s.servers],
            }
            for s in config_result.sources
        ],
        "servers": {
            sid: {
                "name": srv.name,
                "transport": srv.transport,
                "command": srv.command,
                "args": srv.args,
                "url": srv.url,
            }
            for sid, srv in config_result.servers.items()
        },
        "tool_results": [
            {
                "server_id": r.server_id,
                "status": r.status.value,
                "error": r.error,
                "duration_ms": r.duration_ms,
                "tools": [
                    {
                        "name": t.name,
                        "description": t.description,
                        "input_schema": t.input_schema,
                    }
                    for t in r.tools
                ],
            }
            for r in tool_results
        ],
        "duplicates": config_result.duplicates,
    }


def main():
    cli()