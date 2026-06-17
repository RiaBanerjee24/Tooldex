"""
toolpool/_cli_output.py

Formatting helpers for `toolpool discover` CLI output.

Separate from cli.py so the command definitions stay readable and these
display utilities can be tested / reused without touching the CLI wiring.
"""
from __future__ import annotations

import typer

from toolpool.core.discovery.results import ConfigDetectionResult, ToolDiscoveryResult


def print_summary(
    config_result: ConfigDetectionResult,
    tool_results: list[ToolDiscoveryResult],
) -> None:
    """Pretty-print discovery to stdout."""
    typer.echo("")
    typer.echo(typer.style("Config files", bold=True))
    for src in config_result.sources:
        symbol, color = _status_symbol(src.status.value)
        client = src.client.ljust(22)
        summary = _source_line_summary(src)
        typer.echo(f"  {typer.style(symbol, fg=color)}  {client} {summary}")
        if src.error:
            typer.echo(f"     └─ {typer.style(src.error, fg='red', dim=True)}")

    typer.echo("")
    typer.echo(typer.style("Servers & tools", bold=True))
    if not config_result.servers:
        typer.echo("  (none discovered)")
    else:
        tools_by_server = {r.server_id: r for r in tool_results}
        for server_id, server in config_result.servers.items():
            result = tools_by_server.get(server_id)
            display = server.name or server_id
            if result is None:
                typer.echo(f"  •  {display}  (probe skipped)")
                continue
            symbol, color = _status_symbol(result.status.value)
            if result.ok:
                dur = f"{result.duration_ms}ms" if result.duration_ms else ""
                typer.echo(
                    f"  {typer.style(symbol, fg=color)}  "
                    f"{display:<22} {len(result.tools)} tools "
                    f"{typer.style(dur, dim=True)}"
                )
                for tool in result.tools:
                    desc = (tool.description or "").split("\n")[0][:60]
                    typer.echo(f"       · {tool.name}  {typer.style(desc, dim=True)}")
            else:
                typer.echo(
                    f"  {typer.style(symbol, fg=color)}  "
                    f"{display:<22} {result.status.value}"
                )
                if result.error:
                    typer.echo(f"     └─ {typer.style(result.error, fg='red', dim=True)}")

    checked = config_result.checked
    servers = len(config_result.servers)
    found_tools = sum(len(r.tools) for r in tool_results if r.ok)
    typer.echo("")
    typer.echo(typer.style(
        f"Checked {checked} config locations · {servers} servers · {found_tools} tools",
        bold=True,
    ))


def result_as_json(
    config_result: ConfigDetectionResult,
    tool_results: list[ToolDiscoveryResult],
) -> dict:
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
                    {"name": t.name, "description": t.description, "input_schema": t.input_schema}
                    for t in r.tools
                ],
            }
            for r in tool_results
        ],
        "duplicates": config_result.duplicates,
    }


def _status_symbol(status: str) -> tuple[str, str]:
    good = {"found": ("✓", "green"), "empty": ("·", "yellow")}
    if status in good:
        return good[status]
    if status == "not_found":
        return ("✗", "white")
    return ("✗", "red")


def _source_line_summary(src) -> str:
    if src.status.value == "found":
        return f"{len(src.servers)} servers  " + typer.style(src.path, dim=True)
    if src.status.value == "not_found":
        return typer.style(f"{src.path}  (not found)", dim=True)
    if src.status.value == "empty":
        return typer.style(f"{src.path}  (no mcpServers)", dim=True)
    return typer.style(f"{src.path}  ({src.status.value})", fg="red", dim=True)
