from __future__ import annotations
from typing import Literal
from pydantic import BaseModel

class ConflictError(BaseModel):
    """
    Two included files both define the same id.
    Neither wins — entity is shown as conflicted in UI.
    """
    entity_type: Literal["agent", "server"]
    id: str
    files: list[str]
    message: str


class ConflictWarning(BaseModel):
    """
    Root manifest and an included file both define the same id.
    Root wins. UI shows a warning label on the entity.
    """
    entity_type: Literal["agent", "server"]
    id: str
    winner_file: str       # always the root manifest
    loser_file: str
    message: str

# ---------------------------------------------------------------------------
# Orchestration issue models
# ---------------------------------------------------------------------------

class OrchestrationIssue(BaseModel):
    """
    Detected graph issues across the agent fleet.

    type:
      circular     — A → B → A  (two-hop loop, unintentional)
      bidirectional — A → B and B → A but developer used receives_from
                      to signal it's intentional (yellow, not red)
      cycle        — A → B → C → A  (multi-hop loop)

    intentional:
      True when every back-edge in the path was declared via receives_from
    """
    type: Literal["circular", "bidirectional", "cycle"]
    agents: list[str]       # agent ids involved
    path: list[str]         # full path e.g. ["router", "read", "router"]
    intentional: bool       # True → yellow warning, False → red warning