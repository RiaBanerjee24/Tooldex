"""
pericat/cli.py
The `pericat serve` command — the only thing a developer needs to run.
"""
import logging
import uvicorn
import typer

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


@cli.command()
def serve(
    config: str = typer.Option(
        "./pericat.yml", "--config", "-c",
        help="Path to your pericat.yml file"
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

    # load and validate pericat.yml before starting the server
    try:
        parser = init_parser(config)
        manifest = parser.manifest
    except FileNotFoundError as e:
        typer.echo(f"\n  Error: {e}\n", err=True)
        raise typer.Exit(1)
    except ValueError as e:
        typer.echo(f"\n  Config error: {e}\n", err=True)
        raise typer.Exit(1)

    # surface any reference warnings before starting
    warnings = parser.validate_references()
    if warnings:
        typer.echo(f"\n  Warnings in {config}:")
        for w in warnings:
            typer.echo(f"    ⚠  {w}")

    typer.echo(f"""
  ╔══════════════════════════════════════════════════╗
  ║               PERIMETER  v0.1.0                     ║
  ╠══════════════════════════════════════════════════╣
  ║  Config   {config:<39}║
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
        log_level="warning",  # suppress uvicorn noise, we have our own logging
    )


def main():
    cli()