from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel
from pericat.core.models.tool import Tool
from pericat.core.models.policy import AgentPolicy


class FileAccess(BaseModel):
    path: str
    permission: str
    note: Optional[str] = None


class AgentServerRef(BaseModel):
    ref: str                    # must match a server id
    tools: list[Tool] = []


class AgentIdentity(BaseModel):
    type: str = "internal"
    token_lifetime: Optional[str] = None
    client_id: Optional[str] = None
    scopes: list[str] = []
    notes: Optional[str] = None


class AgentOrchestration(BaseModel):
    """
    can_delegate_to:  this agent may hand off tasks TO these agent ids
    receives_from:    explicitly marks that this agent accepts tasks FROM these
                      agent ids — signals intentional bidirectionality
    """
    can_delegate_to: list[str] = []
    receives_from: list[str] = []


class Agent(BaseModel):
    """id is the dict key, populated by the parser."""
    id: str = ""
    name: str
    description: Optional[str] = None
    framework: Optional[str] = None
    status: Literal["active", "inactive", "deprecated"] = "active"
    owner: Optional[str] = None
    tags: list[str] = []
    background: bool = False
    identity: AgentIdentity = AgentIdentity(type="internal")
    policy_engine: Optional[str] = None
    servers: list[AgentServerRef] = []
    file_access: list[FileAccess] = []
    policies: list[AgentPolicy] = []
    orchestration: AgentOrchestration = AgentOrchestration()

    # set by parser — which file this agent was loaded from
    _source_file: str = ""