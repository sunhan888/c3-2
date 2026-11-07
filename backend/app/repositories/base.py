"""저장소 추상화.

Firestore와 로컬 JSON 저장소가 동일한 인터페이스를 구현하도록 정의한다.
덕분에 서비스/라우터 계층은 저장 백엔드를 몰라도 된다.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Iterable


def utcnow_iso() -> str:
    """정렬 가능한 UTC ISO-8601 문자열(마이크로초 포함)."""
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def normalize_message(message: dict) -> dict:
    role = str(message.get("role", "user"))
    if role not in {"user", "assistant", "system"}:
        role = "user"
    return {
        "role": role,
        "content": str(message.get("content", "")),
        "created_at": message.get("created_at") or utcnow_iso(),
    }


def conversation_summary(doc: dict) -> dict:
    messages = doc.get("messages") or []
    preview = ""
    for message in reversed(messages):
        if message.get("role") == "assistant" and message.get("content"):
            preview = str(message["content"]).strip().replace("\n", " ")
            break
    if not preview and messages:
        preview = str(messages[-1].get("content", "")).strip().replace("\n", " ")
    return {
        "id": doc["id"],
        "title": doc.get("title") or "새 대화",
        "message_count": len(messages),
        "preview": preview[:120],
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
        "model": doc.get("model"),
    }


class Store(ABC):
    """데이터/대화 저장소 공통 인터페이스."""

    backend: str = "unknown"

    # ------------------------------------------------------------------ data
    @abstractmethod
    def list_points(self) -> list[dict]:
        """모든 데이터 포인트를 날짜 오름차순으로 반환한다."""

    @abstractmethod
    def get_point(self, point_id: str) -> dict | None: ...

    @abstractmethod
    def find_point_by_date(self, day: str) -> dict | None: ...

    @abstractmethod
    def add_point(self, day: str, value: float, memo: str = "") -> dict: ...

    @abstractmethod
    def update_point(self, point_id: str, changes: dict) -> dict | None: ...

    @abstractmethod
    def delete_point(self, point_id: str) -> bool: ...

    @abstractmethod
    def bulk_add_points(self, rows: Iterable[tuple[str, float, str]]) -> int: ...

    @abstractmethod
    def count_points(self) -> int: ...

    # --------------------------------------------------------- conversations
    @abstractmethod
    def list_conversations(self, limit: int, offset: int) -> tuple[list[dict], int]: ...

    @abstractmethod
    def get_conversation(self, conversation_id: str) -> dict | None: ...

    @abstractmethod
    def create_conversation(
        self, title: str, messages: list[dict], model: str | None = None
    ) -> dict: ...

    @abstractmethod
    def append_messages(
        self, conversation_id: str, messages: list[dict], model: str | None = None
    ) -> dict | None: ...

    @abstractmethod
    def rename_conversation(self, conversation_id: str, title: str) -> dict | None: ...

    @abstractmethod
    def delete_conversation(self, conversation_id: str) -> bool: ...

    @abstractmethod
    def count_conversations(self) -> int: ...

    # --------------------------------------------------------------- helpers
    @staticmethod
    def sort_by_date(points: list[dict], reverse: bool = False) -> list[dict]:
        return sorted(points, key=lambda item: (str(item.get("date", "")), item.get("id", "")), reverse=reverse)
