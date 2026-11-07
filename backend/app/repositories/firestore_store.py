"""Firestore 저장소.

컬렉션 구조
    data/{pointId}           : {date, value, memo, created_at, updated_at}
    conversations/{convId}   : {title, messages[], model, created_at, updated_at}

서비스 계정 키는 환경 변수에서 읽어 초기화하며(코드 하드코딩 금지),
문서 ID는 12자리 hex로 통일해 로컬 저장소와 응답 형태를 일치시킨다.
"""

from __future__ import annotations

import logging
from typing import Iterable

import firebase_admin
from firebase_admin import credentials, firestore

from app.repositories.base import Store, conversation_summary, new_id, normalize_message, utcnow_iso

logger = logging.getLogger(__name__)

DATA_COLLECTION = "data"
CONVERSATION_COLLECTION = "conversations"


class FirestoreStore(Store):
    backend = "firestore"

    def __init__(self, service_account: dict, project_id: str | None = None) -> None:
        self._client = self._init_client(service_account, project_id)
        self._data = self._client.collection(DATA_COLLECTION)
        self._conversations = self._client.collection(CONVERSATION_COLLECTION)

    @staticmethod
    def _init_client(service_account: dict, project_id: str | None):
        options = {"projectId": project_id} if project_id else None
        try:
            app = firebase_admin.get_app()
        except ValueError:
            cred = credentials.Certificate(service_account)
            app = firebase_admin.initialize_app(cred, options)
        return firestore.client(app=app)

    # ------------------------------------------------------------------ data
    def list_points(self) -> list[dict]:
        points = []
        for snapshot in self._data.stream():
            payload = snapshot.to_dict() or {}
            payload["id"] = snapshot.id
            points.append(payload)
        return self.sort_by_date(points)

    def get_point(self, point_id: str) -> dict | None:
        snapshot = self._data.document(point_id).get()
        if not snapshot.exists:
            return None
        payload = snapshot.to_dict() or {}
        payload["id"] = snapshot.id
        return payload

    def find_point_by_date(self, day: str) -> dict | None:
        query = self._data.where("date", "==", day).limit(1).stream()
        for snapshot in query:
            payload = snapshot.to_dict() or {}
            payload["id"] = snapshot.id
            return payload
        return None

    def add_point(self, day: str, value: float, memo: str = "") -> dict:
        now = utcnow_iso()
        payload = {
            "date": day,
            "value": float(value),
            "memo": memo or "",
            "created_at": now,
            "updated_at": now,
        }
        document_id = new_id()
        self._data.document(document_id).set(payload)
        payload["id"] = document_id
        return payload

    def update_point(self, point_id: str, changes: dict) -> dict | None:
        reference = self._data.document(point_id)
        snapshot = reference.get()
        if not snapshot.exists:
            return None
        payload = {key: value for key, value in changes.items() if value is not None}
        if "value" in payload:
            payload["value"] = float(payload["value"])
        payload["updated_at"] = utcnow_iso()
        reference.update(payload)
        merged = snapshot.to_dict() or {}
        merged.update(payload)
        merged["id"] = point_id
        return merged

    def delete_point(self, point_id: str) -> bool:
        reference = self._data.document(point_id)
        if not reference.get().exists:
            return False
        reference.delete()
        return True

    def bulk_add_points(self, rows: Iterable[tuple[str, float, str]]) -> int:
        now = utcnow_iso()
        existing = {str(point.get("date")) for point in self.list_points()}
        batch = self._client.batch()
        created = 0
        for day, value, memo in rows:
            if day in existing:
                continue
            document_id = new_id()
            batch.set(
                self._data.document(document_id),
                {
                    "date": day,
                    "value": float(value),
                    "memo": memo or "",
                    "created_at": now,
                    "updated_at": now,
                },
            )
            created += 1
            if created % 400 == 0:  # Firestore 배치 쓰기 제한(500) 여유 확보
                batch.commit()
                batch = self._client.batch()
        if created:
            batch.commit()
        return created

    def count_points(self) -> int:
        aggregate = self._data.count().get()
        try:
            return int(aggregate[0][0].value)
        except (TypeError, IndexError):  # 이전 버전 SDK 호환
            return sum(1 for _ in self._data.stream())

    # --------------------------------------------------------- conversations
    def list_conversations(self, limit: int, offset: int) -> tuple[list[dict], int]:
        documents = []
        for snapshot in self._conversations.order_by(
            "updated_at", direction=firestore.Query.DESCENDING
        ).stream():
            payload = snapshot.to_dict() or {}
            payload["id"] = snapshot.id
            documents.append(payload)
        total = len(documents)
        window = documents[offset : offset + limit]
        return [conversation_summary(item) for item in window], total

    def get_conversation(self, conversation_id: str) -> dict | None:
        snapshot = self._conversations.document(conversation_id).get()
        if not snapshot.exists:
            return None
        payload = snapshot.to_dict() or {}
        payload["id"] = snapshot.id
        return payload

    def create_conversation(
        self, title: str, messages: list[dict], model: str | None = None
    ) -> dict:
        now = utcnow_iso()
        payload = {
            "title": title,
            "messages": [normalize_message(message) for message in messages],
            "model": model,
            "created_at": now,
            "updated_at": now,
        }
        document_id = new_id()
        self._conversations.document(document_id).set(payload)
        payload["id"] = document_id
        return payload

    def append_messages(
        self, conversation_id: str, messages: list[dict], model: str | None = None
    ) -> dict | None:
        reference = self._conversations.document(conversation_id)
        snapshot = reference.get()
        if not snapshot.exists:
            return None
        payload = snapshot.to_dict() or {}
        merged_messages = list(payload.get("messages") or [])
        merged_messages.extend(normalize_message(message) for message in messages)
        update = {"messages": merged_messages, "updated_at": utcnow_iso()}
        if model:
            update["model"] = model
        reference.update(update)
        payload.update(update)
        payload["id"] = conversation_id
        return payload

    def rename_conversation(self, conversation_id: str, title: str) -> dict | None:
        reference = self._conversations.document(conversation_id)
        snapshot = reference.get()
        if not snapshot.exists:
            return None
        reference.update({"title": title, "updated_at": utcnow_iso()})
        payload = snapshot.to_dict() or {}
        payload.update({"title": title, "updated_at": utcnow_iso()})
        payload["id"] = conversation_id
        return payload

    def delete_conversation(self, conversation_id: str) -> bool:
        reference = self._conversations.document(conversation_id)
        if not reference.get().exists:
            return False
        reference.delete()
        return True

    def count_conversations(self) -> int:
        aggregate = self._conversations.count().get()
        try:
            return int(aggregate[0][0].value)
        except (TypeError, IndexError):
            return sum(1 for _ in self._conversations.stream())
