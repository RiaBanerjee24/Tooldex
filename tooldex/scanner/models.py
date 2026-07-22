from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class RiskLevel(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH     = "HIGH"
    MEDIUM   = "MEDIUM"
    LOW      = "LOW"
    CLEAN    = "CLEAN"


@dataclass
class RiskFlag:
    tool_name:    str
    rule_id:      str
    severity:     RiskLevel
    matched_text: str
    message:      str


@dataclass
class ServerRiskReport:
    server_id:    str
    overall_risk: RiskLevel
    flags:        list[RiskFlag] = field(default_factory=list)
