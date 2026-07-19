from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api import router
from .note_api import router as note_router
from .presentation_api import router as presentation_router
from .catalog import seed_catalog
from .config import ROOT_DIR
from .database import SessionLocal, init_db
from .deepwiki_service import repair_incomplete_wikis
from .domain_pack_service import seed_domain_packs
from .library_service import ensure_library_membership_migration
from .scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    db = SessionLocal()
    try:
        seed_catalog(db)
        seed_domain_packs(db)
        ensure_library_membership_migration(db)
        repair_incomplete_wikis(db)
    finally:
        db.close()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="PaperMorrow API",
    version="0.4.0",
    description="AI 论文推荐、学习笔记与 DeepWiki 代码解析",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
app.include_router(note_router)
app.include_router(presentation_router)

dist_dir = ROOT_DIR / "frontend" / "dist"
if dist_dir.exists():
    assets_dir = dist_dir / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        candidate = (dist_dir / full_path).resolve()
        if candidate.is_file() and dist_dir.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(dist_dir / "index.html")
else:
    @app.get("/", include_in_schema=False)
    def root():
        return {"message": "PaperMorrow API is running", "docs": "/docs", "frontend": "Run npm --prefix frontend run build"}
