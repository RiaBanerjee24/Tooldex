"""GET /api/health"""
from fastapi import APIRouter
from toolpool.core.parsers.parser import get_parser
from toolpool import version

router = APIRouter()

@router.get("/health")
async def health():
    parser = get_parser()
    manifest = parser.manifest
    warnings = parser.validate_references()
    return {
        "status": "degraded" if warnings else "ok",
        "toolpool": version,
        "config": {
            "name": manifest.metadata.name,
            "description": manifest.metadata.description,
            "owner": manifest.metadata.owner,
            "updated": manifest.metadata.updated,
            "agents": len(manifest.agents),
            "servers": len(manifest.servers),
            "policy_engines": len(manifest.policy_engines),
        },
        "warnings": warnings,
    }