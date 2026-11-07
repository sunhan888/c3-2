"""상태 확인 및 메타 정보 API."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app.api.deps import settings_dependency, store_dependency
from app.core.config import Settings
from app.models.schemas import HealthOut
from app.repositories.base import Store

router = APIRouter(prefix="/api", tags=["상태"])


@router.get("/health", response_model=HealthOut, summary="헬스 체크")
def health(store: Store = Depends(store_dependency), settings: Settings = Depends(settings_dependency)) -> dict:
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.app_version,
        "storage_backend": store.backend,
        "model": settings.openai_model,
        "tools_enabled": settings.tools_enabled,
        "data_points": store.count_points(),
        "conversations": store.count_conversations(),
        "llm_configured": bool(settings.openai_api_key),
        "time": datetime.now(timezone.utc),
    }


@router.get("/meta", summary="서비스 메타 정보")
def meta(store: Store = Depends(store_dependency), settings: Settings = Depends(settings_dependency)) -> dict:
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "topic": settings.data_topic,
        "unit": settings.data_unit,
        "storage": store.backend,
        "llm": {
            "model": settings.openai_model,
            "configured": bool(settings.openai_api_key),
            "tools_enabled": settings.tools_enabled,
            "max_tokens": settings.openai_max_tokens,
        },
        "endpoints": [
            "GET /api/data",
            "POST /api/data",
            "PUT /api/data/{id}",
            "DELETE /api/data/{id}",
            "GET /api/data/summary",
            "GET /api/data/statistics",
            "GET /api/data/export",
            "GET /api/conversations",
            "POST /api/conversations",
            "GET /api/conversations/{id}",
            "DELETE /api/conversations/{id}",
            "POST /api/chat",
        ],
    }
