from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field

class PolicyEngine(BaseModel):
    """
    id is the dict key in pericat.yml, not a field.
    Populated by the parser after loading.
    """
    id: str = ""
    engine: str                               # "opa", "cedar", "casbin", etc.
    type: Literal["file", "http", "inline"]
    source: str
    description: Optional[str] = None
    policy_path: str = "agent.authz.allow"

# ---------------------------------------------------------------------------
# Inline policy
# ---------------------------------------------------------------------------

class InlinePolicyRule(BaseModel):
    tool: str
    access: Literal["allowed", "denied"]
    reason: Optional[str] = None


class AgentPolicy(BaseModel):
    ref: Optional[str] = None
    description: Optional[str] = None
    rules: list[InlinePolicyRule] = []
