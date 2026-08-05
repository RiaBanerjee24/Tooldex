"""GET /api/health"""
import time
from datetime import datetime, timezone

from fastapi import APIRouter
from tooldex.core.parsers.parser import get_startup_time

router = APIRouter()


@router.get("/health")
async def health():
    startup = get_startup_time()
    uptime = int(time.monotonic() - startup) if startup is not None else None
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "uptime_seconds": uptime,
    }
