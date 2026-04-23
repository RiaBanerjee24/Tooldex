from __future__ import annotations
from pydantic import BaseModel

class Observatory(BaseModel):
    audit_log: str = "./logs/audit.log"
    changes_log: str = "./logs/changes.txt"