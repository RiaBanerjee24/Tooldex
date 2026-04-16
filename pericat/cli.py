"""
pericat/cli.py
The `pericat run` command — the only thing a developer needs to run.
"""
import logging
import uvicorn
import typer
from typing import Optional
from pathlib import Path

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
    from pericat.core.parsers.parser import init_parser
    from pericat.api.app import create_app
 
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

def main():
    cli()