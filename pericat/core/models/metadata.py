from __future__ import annotations
from typing import Optional
from pydantic import BaseModel

class PericatMetadata(BaseModel):
    name: str
    description: Optional[str] = None
    owner: Optional[str] = None
    updated: Optional[str] = None