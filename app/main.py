from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.database import database_connection, init_db
from app.routers import itineraries, places, posts
from app.services.data_importer import ensure_places_loaded


logger = logging.getLogger("coursetalk")
settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    if settings.auto_import_data:
        try:
            with database_connection() as db:
                imported = ensure_places_loaded(
                    db,
                    settings.resolved_data_zip_path,
                    settings.import_regions,
                )
                if imported:
                    logger.info("공공데이터 장소 %s건을 적재했습니다.", imported)
        except Exception:
            logger.exception("장소 데이터 자동 적재에 실패했습니다.")
    yield


app = FastAPI(
    title=settings.app_name,
    version="1.1.0",
    description="공공데이터 기반 AI 여행 일정 및 익명 커뮤니티 API",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok", "service": settings.app_name}

@app.get("/")
def root():
    return {
        "status": "running",
        "service": settings.app_name
    }


app.include_router(places.router, prefix="/api")
app.include_router(itineraries.router, prefix="/api")
app.include_router(posts.router, prefix="/api")
