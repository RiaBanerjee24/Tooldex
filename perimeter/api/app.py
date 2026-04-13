"""
perimeter/api/app.py
FastAPI application factory.
Registers all routers and serves the pre-built React UI.
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from perimeter.core.parser import get_parser
from perimeter.api.routers import health, agents, servers, policy
from perimeter import settings

logger = logging.getLogger("perimeter.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # start watching perimeter.yml for changes in the background
    watch_task = asyncio.create_task(get_parser().watch())
    logger.info("Perimeter started")
    yield
    watch_task.cancel()
    logger.info("Perimeter stopped")   


def create_app() -> FastAPI:
    app = FastAPI(
        title="Perimeter",
        description="AI Agent Permission Observatory",
        version="0.1.0",
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
    app.include_router(agents.router,  prefix="/api", tags=["agents"])
    app.include_router(servers.router, prefix="/api", tags=["servers"])
    app.include_router(policy.router,  prefix="/api", tags=["policy"])


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