"""대화 기록 API.

목록(GET /api/conversations)은 messages를 포함하지 않고,
특정 대화 조회(GET /api/conversations/{id})가 전체 messages를 반환한다. (요구사항 A 방식)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import store_dependency
from app.models.schemas import (
    ConversationCreate,
    ConversationDetail,
    ConversationListOut,
    ConversationUpdate,
)
from app.repositories.base import Store, conversation_summary
from app.services.chat_service import make_title

router = APIRouter(prefix="/api/conversations", tags=["대화 기록"])


def _detail(doc: dict) -> dict:
    payload = conversation_summary(doc)
    payload["messages"] = doc.get("messages", [])
    return payload


@router.post(
    "",
    response_model=ConversationDetail,
    status_code=status.HTTP_201_CREATED,
    summary="대화 저장",
    description="새 대화를 저장합니다. messages를 비우면 빈 대화가 만들어집니다.",
)
def create_conversation(payload: ConversationCreate, store: Store = Depends(store_dependency)) -> dict:
    messages = [message.model_dump() for message in payload.messages]
    title = payload.title
    if not title:
        first_user = next((m for m in messages if m["role"] == "user"), None)
        title = make_title(first_user["content"]) if first_user else "새 대화"
    doc = store.create_conversation(title=title, messages=messages)
    return _detail(doc)


@router.get(
    "",
    response_model=ConversationListOut,
    summary="대화 목록 조회",
    description="최신 갱신순으로 대화 목록을 반환합니다. messages는 포함되지 않습니다.",
)
def list_conversations(
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    store: Store = Depends(store_dependency),
) -> dict:
    items, total = store.list_conversations(limit=limit, offset=offset)
    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "includes_messages": False,
    }


@router.get(
    "/{conversation_id}",
    response_model=ConversationDetail,
    summary="특정 대화 불러오기",
    description="대화의 전체 메시지를 반환합니다.",
)
def get_conversation(conversation_id: str, store: Store = Depends(store_dependency)) -> dict:
    doc = store.get_conversation(conversation_id)
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "해당 대화를 찾을 수 없습니다."},
        )
    return _detail(doc)


@router.patch(
    "/{conversation_id}",
    response_model=ConversationDetail,
    summary="대화 제목 수정",
)
def rename_conversation(
    conversation_id: str, payload: ConversationUpdate, store: Store = Depends(store_dependency)
) -> dict:
    doc = store.rename_conversation(conversation_id, payload.title)
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "해당 대화를 찾을 수 없습니다."},
        )
    return _detail(doc)


@router.delete(
    "/{conversation_id}",
    summary="대화 삭제",
)
def delete_conversation(conversation_id: str, store: Store = Depends(store_dependency)) -> dict:
    if not store.delete_conversation(conversation_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "해당 대화를 찾을 수 없습니다."},
        )
    return {"deleted": True, "id": conversation_id}
