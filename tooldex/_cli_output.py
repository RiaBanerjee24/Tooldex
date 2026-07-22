"""
tooldex/_cli_output.py

Formatting helpers for `tooldex run` CLI output.

Separate from cli.py so the command definitions stay readable and these
display utilities can be tested / reused without touching the CLI wiring.
"""
from __future__ import annotations

import typer

from tooldex.core.discovery.results import ConfigDetectionResult, ToolDiscoveryResult


def print_banner(server_count: int, tool_count: int, url: str) -> None:
    """Print the tooldex startup/rescan box to stdout."""
    from tooldex import __version__

    def _row(text: str, width: int = 50) -> str:
        if len(text) > width:
            text = text[: width - 1] + "…"
        return f"║{text.ljust(width)}║"

    typer.echo("\n  " + "╔" + "═" * 50 + "╗")
    typer.echo("  " + _row(f"         tooldex  v{__version__}"))
    typer.echo("  " + "╠" + "═" * 50 + "╣")
    typer.echo("  " + _row(f"  Servers  {server_count}"))
    typer.echo("  " + _row(f"  Tools    {tool_count}"))
    typer.echo("  " + "╠" + "═" * 50 + "╣")
    typer.echo("  " + _row(f"  →  {url}"))
    typer.echo("  " + "╚" + "═" * 50 + "╝\n")


_CLIENT_DISPLAY = {
    "antigravity_user":      "gemini (antigravity)",
    "antigravity_project":   "gemini (antigravity)",
    "mcp_json_bare_project": "mcp.json",
    "agents_user":            "agents",
    "agents_user_dotfile":    "agents",
    "agents_project":         "agents",
    "agents_project_dotfile": "agents",
}


_RISK_STYLE = {
    "CRITICAL": {"fg": "red",    "bold": True},
    "HIGH":     {"fg": "red",    "bold": False},
    "MEDIUM":   {"fg": "yellow", "bold": False},
    "LOW":      {"fg": "cyan",   "bold": False},
    "INFO":     {"fg": "white",  "bold": False},
    "CLEAN":    {"fg": "green",  "bold": False},
}

_SEVERITY_RANK = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}


def _worst_severity(severities: list[str]) -> str:
    if not severities:
        return "LOW"
    return min(severities, key=lambda s: _SEVERITY_RANK.get(s.upper(), 99))


def print_summary(
    config_result: ConfigDetectionResult,
    tool_results: list[ToolDiscoveryResult],
    scan_results: dict | None = None,
) -> None:
    """Pretty-print discovery to stdout."""
    typer.echo("")
    typer.echo(typer.style("Config files", bold=True))
    for src in config_result.sources:
        symbol, color = _status_symbol(src.status.value)
        client = _CLIENT_DISPLAY.get(src.client, src.client).ljust(22)
        summary = _source_line_summary(src)
        typer.echo(f"  {typer.style(symbol, fg=color)}  {client} {summary}")
        if src.error:
            is_hard_error = src.status.value in ("parse_error", "read_error")
            style_kw = {"fg": "red", "bold": True} if is_hard_error else {"fg": "red", "dim": True}
            typer.echo(f"     └─ {typer.style(src.error, **style_kw)}")

    typer.echo("")
    typer.echo(typer.style("Servers", bold=True))
    if not config_result.servers:
        typer.echo("  (none discovered)")
    else:
        tools_by_server = {r.server_id: r for r in tool_results}
        for server_id, server in config_result.servers.items():
            result = tools_by_server.get(server_id)
            display = server.name or server_id
            if result is None:
                typer.echo(f"  •  {display:<22}  (probe skipped)")
                continue
            symbol, color = _status_symbol(result.status.value)
            if result.ok:
                dur = f"  {typer.style(str(result.duration_ms) + 'ms', dim=True)}" if result.duration_ms else ""
                typer.echo(
                    f"  {typer.style(symbol, fg=color)}  "
                    f"{display:<22} {len(result.tools)} tools{dur}"
                )
            else:
                typer.echo(
                    f"  {typer.style(symbol, fg=color)}  "
                    f"{display:<22} {result.status.value}"
                )
                if result.error:
                    typer.echo(f"     └─ {typer.style(result.error, fg='red', dim=True)}")

    if scan_results:
        typer.echo("")
        typer.echo(typer.style("Security", bold=True))

        flagged_servers = {
            sid: [t for t in tools if not t.is_safe]
            for sid, tools in scan_results.items()
            if any(not t.is_safe for t in tools)
        }
        clean_count = len(scan_results) - len(flagged_servers)

        if not flagged_servers:
            typer.echo(
                f"  {typer.style('✓', fg='green')}  "
                f"All {len(scan_results)} scanned servers clean"
            )
        else:
            if clean_count:
                typer.echo(
                    f"  {typer.style('✓', fg='green')}  "
                    f"{clean_count} server{'s' if clean_count != 1 else ''} clean"
                )
            for server_id, flagged_tools in flagged_servers.items():
                severities = [f.severity for t in flagged_tools for f in t.findings]
                worst = _worst_severity(severities)
                style = _RISK_STYLE.get(worst, {"fg": "yellow", "bold": False})
                typer.echo(
                    f"  {typer.style('⚠', fg=style['fg'], bold=style['bold'])}  "
                    f"{server_id:<38} "
                    f"{typer.style(worst, **style)}"
                )
                for tool_result in flagged_tools:
                    for finding in tool_result.findings:
                        f_style = _RISK_STYLE.get(finding.severity, {"fg": "yellow", "bold": False})
                        typer.echo(
                            f"     └─ {typer.style(finding.severity, **f_style)}"
                            f"  [{finding.analyzer}]  {finding.threat_category}"
                        )
                        typer.echo(
                            f"        {typer.style(finding.summary, dim=True)}"
                        )

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
                "in_file_duplicates": s.in_file_duplicates,
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
        "duplicates": config_result.duplicates,
    }


def _status_symbol(status: str) -> tuple[str, str]:
    table = {
        "found":       ("✓", "green"),
        "empty":       ("·", "yellow"),
        "not_found":   ("·", "white"),
        "parse_error": ("✗", "red"),
        "read_error":  ("✗", "red"),
    }
    return table.get(status, ("✗", "red"))


def _source_line_summary(src) -> str:
    if src.status.value == "found":
        return f"{len(src.servers)} servers  " + typer.style(src.path, dim=True)
    if src.status.value == "not_found":
        return typer.style(f"{src.path}  (not found)", dim=True)
    if src.status.value == "empty":
        return typer.style(f"{src.path}  (no servers)", dim=True)
    if src.status.value == "parse_error":
        return typer.style(f"{src.path}  (parse error)", fg="red")
    if src.status.value == "read_error":
        return typer.style(f"{src.path}  (read error)", fg="red")
    return typer.style(f"{src.path}  ({src.status.value})", fg="red", dim=True)
