"""GET /api/files/"""
from fastapi import APIRouter
from tooldex.core.parsers.parser import get_discovery_sources
from tooldex.core.discovery.results import SourceStatus

router = APIRouter()


@router.get("/files")
async def list_files():
    sources = get_discovery_sources()
    files = []
    for s in sources:
        status = s.status.value if isinstance(s.status, SourceStatus) else str(s.status)
        files.append({
            "client": s.client,
            "path": s.path,
            "status": status,
            "server_count": len(s.servers),
            "server_ids": [srv.id for srv in s.servers],
            "error": s.error or None,
            "in_file_duplicates": s.in_file_duplicates,
        })

    return {
        "files": files,
        "total": len(files),
        "found": sum(1 for s in sources if s.ok),
        "not_found": sum(1 for s in sources if s.status == SourceStatus.NOT_FOUND),
        "errors": sum(1 for s in sources if s.status in (SourceStatus.PARSE_ERROR, SourceStatus.READ_ERROR)),
    }
