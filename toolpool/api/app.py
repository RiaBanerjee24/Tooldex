"""
toolpool/api/app.py
FastAPI application factory.
Registers all routers and serves the pre-built React UI.
"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from toolpool.api.routers import health, servers, files
from toolpool import settings, version

logger = logging.getLogger("toolpool.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="toolpool",
        description="Unified MCP Server Discovery",
        version=version,
        docs_url="/api/docs" if settings.debug else None,
        redoc_url="/api/redoc" if settings.debug else None,
        openapi_url="/api/openapi.json" if settings.debug else None,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=True,
    )

    # API routes
    app.include_router(health.router,  prefix="/api", tags=["health"])
    app.include_router(servers.router, prefix="/api", tags=["servers"])
    app.include_router(files.router,   prefix="/api", tags=["files"])


    # Serve pre-built React UI
    # In dev: not present, Vite dev server handles it
    # In production: npm run build output committed to this folder
    ui_dist = Path(__file__).parent.parent / "ui" / "dist"
    if ui_dist.exists():
        app.mount(
            "/assets",
            StaticFiles(directory=ui_dist / "assets"),
            name="assets",
        )

        @app.get("/", include_in_schema=False)
        @app.get("/{path:path}", include_in_schema=False)
        async def serve_ui(path: str = ""):
            file = ui_dist / path
            if file.exists() and file.is_file():
                return FileResponse(file)
            return FileResponse(ui_dist / "index.html")

    return app