from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel


class ToolPermission(BaseModel):
    operations: list[str]
    on: str = "*"
    access: Literal["allowed", "denied"]


class Tool(BaseModel):
    name: str
    description: Optional[str] = None
    risk: Optional[Literal["low", "medium", "high", "critical"]] = None
    access: Optional[Literal["allowed", "denied"]] = None
    permissions: list[ToolPermission] = []
    denied_by: Optional[str] = None

    def effective_access(self) -> str:
        if self.access:
            return self.access
        if not self.permissions:
            return "unknown"
        has_allowed = any(p.access == "allowed" for p in self.permissions)
        has_denied  = any(p.access == "denied"  for p in self.permissions)
        if has_allowed and has_denied:
            return "partial"
        return "allowed" if has_allowed else "denied"
