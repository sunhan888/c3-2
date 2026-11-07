"""FastAPI 애플리케이션 팩토리."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.repositories.factory import get_store
from app.routers import chat, conversations, data, meta
from app.services.bootstrap import ensure_seed_data

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

DESCRIPTION = """
**DataMate** — 내 데이터를 이해하는 AI 비서 API.

* `POST /api/chat` : 데이터 요약을 시스템 프롬프트에 주입해 GPT가 맞춤 답변을 생성합니다.
* `GET /api/data/summary` : 기간/개수/통계/트렌드 요약(채팅 컨텍스트와 동일한 소스)
* `/api/data`, `/api/conversations` : CRUD 및 대화 기록 API
* `GET /docs` : Swagger UI
""".strip()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    store = get_store()
    created = ensure_seed_data(store, settings)
    logger.info(
        "기동 완료 | 저장소=%s | 모델=%s | 데이터=%s건(+%s) | 도구=%s",
        store.backend,
        settings.openai_model,
        store.count_points(),
        created,
        settings.tools_enabled,
    )
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=DESCRIPTION,
        lifespan=lifespan,
        contact={"name": "DataMate", "url": "https://github.com/sunhan888/c3-2"},
        openapi_tags=[
            {"name": "AI 채팅", "description": "컨텍스트 주입 기반 대화 API"},
            {"name": "데이터", "description": "시계열 데이터 CRUD 및 요약/통계"},
            {"name": "대화 기록", "description": "대화 저장/조회/삭제"},
            {"name": "상태", "description": "헬스 체크 및 메타 정보"},
        ],
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition"],
    )

    app.include_router(meta.router)
    app.include_router(data.router)
    app.include_router(conversations.router)
    app.include_router(chat.router)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "code": "validation_error",
                "message": "입력 값이 올바르지 않습니다. 날짜 형식(YYYY-MM-DD)과 값 범위를 확인해 주세요.",
                "detail": jsonable_encoder(exc.errors()),
            },
        )

    # 로컬 개발 편의를 위해 같은 서버에서 프론트엔드도 서빙한다(선택 기능).
    if settings.serve_frontend and (settings.frontend_dir / "index.html").exists():
        app.mount(
            "/",
            StaticFiles(directory=str(settings.frontend_dir), html=True),
            name="frontend",
        )
        logger.info("프론트엔드 정적 파일을 / 에 마운트했습니다: %s", settings.frontend_dir)
    else:
        @app.get("/", include_in_schema=False)
        def root() -> dict:
            return {
                "service": settings.app_name,
                "docs": "/docs",
                "health": "/api/health",
            }

    return app


app = create_app()
