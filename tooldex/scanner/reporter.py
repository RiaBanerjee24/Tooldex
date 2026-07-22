from __future__ import annotations

import typer

from .models import RiskLevel, ServerRiskReport

_RISK_STYLE: dict[RiskLevel, dict] = {
    RiskLevel.CRITICAL: {"fg": "red",     "bold": True},
    RiskLevel.HIGH:     {"fg": "red",     "bold": False},
    RiskLevel.MEDIUM:   {"fg": "yellow",  "bold": False},
    RiskLevel.LOW:      {"fg": "cyan",    "bold": False},
    RiskLevel.CLEAN:    {"fg": "green",   "bold": False},
}

_RISK_LABEL = {
    RiskLevel.CRITICAL: "CRITICAL",
    RiskLevel.HIGH:     "HIGH    ",
    RiskLevel.MEDIUM:   "MEDIUM  ",
    RiskLevel.LOW:      "LOW     ",
    RiskLevel.CLEAN:    "CLEAN   ",
}


def print_report(reports: list[ServerRiskReport]) -> None:
    typer.echo("")
    typer.echo(typer.style("Security scan", bold=True))

    if not reports:
        typer.echo("  (no servers to scan)")
        return

    for report in reports:
        style = _RISK_STYLE[report.overall_risk]
        label = _RISK_LABEL[report.overall_risk]
        typer.echo(
            f"  {typer.style(label, **style)}  {report.server_id}"
        )
        for flag in report.flags:
            flag_style = _RISK_STYLE[flag.severity]
            typer.echo(
                f"     └─ {typer.style(flag.severity.value, **flag_style)}"
                f"  [{flag.rule_id}]  {flag.message}"
            )
            if flag.matched_text:
                typer.echo(
                    f"        matched: {typer.style(flag.matched_text, dim=True)}"
                )
