from __future__ import annotations
from typing import Literal
from pydantic import BaseModel


class ConflictError(BaseModel):
    """Two included files both define the same id. Neither wins."""
    entity_type: Literal["agent", "server"]
    id: str
    files: list[str]
    message: str


class ConflictWarning(BaseModel):
    """Root manifest and an included file both define the same id. Root wins."""
    entity_type: Literal["agent", "server"]
    id: str
    winner_file: str
    loser_file: str
    message: str


class OrchestrationIssue(BaseModel):
    """
    Detected graph issue in the agent delegation graph.

    type:
      circular     — A → B → A  (two-hop loop, unintentional)
      bidirectional — A → B → A with receives_from declared (intentional, yellow)
      cycle        — A → B → C → A  (multi-hop loop)

    intentional: True → yellow warning, False → red error
    """
    type: Literal["circular", "bidirectional", "cycle"]
    agents: list[str]
    path: list[str]
    intentional: bool