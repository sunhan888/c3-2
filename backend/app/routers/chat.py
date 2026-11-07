"""AI 채팅 API (컨텍스트 주입 + 자동 저장)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import settings_dependency, store_dependency
from app.core.config import Settings
from app.models.schemas import ChatRequest, ChatResponse
from app.repositories.base import Store
from app.services.chat_service import ChatService

router = APIRouter(prefix="/api", tags=["AI 채팅"])


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="AI에게 데이터 기반 질문",
    description=(
        "저장된 데이터 요약을 시스템 프롬프트에 주입한 뒤 GPT에 질문합니다. "
        "필요하면 모델이 내부 도구(요약/통계/데이터 조회)를 호출하며, "
        "대화는 conversations 컬렉션에 자동 저장됩니다."
    ),
)
def chat(
    payload: ChatRequest,
    store: Store = Depends(store_dependency),
    settings: Settings = Depends(settings_dependency),
) -> dict:
    service = ChatService(store, settings)
    return service.chat(payload)
