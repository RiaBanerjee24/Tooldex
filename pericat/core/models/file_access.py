from __future__ import annotations
from typing import Optional
from pydantic import BaseModel


class FileAccess(BaseModel):
    path: str
    permission: str
    note: Optional[str] = None