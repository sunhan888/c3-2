"""로컬 JSON 저장소.

Firebase 자격 증명이 없는 환경(로컬 개발, 코드 리뷰)에서도 서비스 전체 기능을
검증할 수 있도록 파일 기반 저장소를 제공한다. Firestore와 동일한 인터페이스를
구현하므로 저장 백엔드만 바꿔 끼울 수 있다.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Iterable

from app.repositories.base import Store, conversation_summary, new_id, normalize_message, utcnow_iso


class LocalStore(Store):
    backend = "local"

    def __init__(self, directory: Path) -> None:
        self._directory = Path(directory)
        self._directory.mkdir(parents=True, exist_ok=True)
        self._path = self._directory / "store.json"
        self._lock = threading.RLock()
        self._state: dict[str, list[dict]] = {"data": [], "conversations": []}
        self._load()

    # ------------------------------------------------------------ persistence
    def _load(self) -> None:
        if not self._path.exists():
            self._flush()
            return
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            payload = {}
        self._state = {
            "data": list(payload.get("data", [])),
            "conversations": list(payload.get("conversations", [])),
        }

    def _flush(self) -> None:
        tmp_path = self._path.with_suffix(".json.tmp")
        tmp_path.write_text(
            json.dumps(self._state, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(tmp_path, self._path)

    # ------------------------------------------------------------------ data
    def list_points(self) -> list[dict]:
        with self._lock:
            points = [dict(item) for item in self._state["data"]]
        return self.sort_by_date(points)

    def get_point(self, point_id: str) -> dict | None:
        with self._lock:
            for item in self._state["data"]:
                if item["id"] == point_id:
                    return dict(item)
        return None

    def find_point_by_date(self, day: str) -> dict | None:
        with self._lock:
            for item in self._state["data"]:
                if str(item.get("date")) == day:
                    return dict(item)
        return None

    def add_point(self, day: str, value: float, memo: str = "") -> dict:
        now = utcnow_iso()
        record = {
            "id": new_id(),
            "date": day,
            "value": float(value),
            "memo": memo or "",
            "created_at": now,
            "updated_at": now,
        }
        with self._lock:
            self._state["data"].append(record)
            self._flush()
        return dict(record)

    def update_point(self, point_id: str, changes: dict) -> dict | None:
        with self._lock:
            for item in self._state["data"]:
                if item["id"] == point_id:
                    for key in ("date", "value", "memo"):
                        if key in changes and changes[key] is not None:
                            item[key] = float(changes[key]) if key == "value" else changes[key]
                    item["updated_at"] = utcnow_iso()
                    self._flush()
                    return dict(item)
        return None

    def delete_point(self, point_id: str) -> bool:
        with self._lock:
            before = len(self._state["data"])
            self._state["data"] = [item for item in self._state["data"] if item["id"] != point_id]
            deleted = len(self._state["data"]) != before
            if deleted:
                self._flush()
            return deleted

    def bulk_add_points(self, rows: Iterable[tuple[str, float, str]]) -> int:
        now = utcnow_iso()
        created = 0
        with self._lock:
            existing = {str(item.get("date")) for item in self._state["data"]}
            for day, value, memo in rows:
                if day in existing:
                    continue
                self._state["data"].append(
                    {
                        "id": new_id(),
                        "date": day,
                        "value": float(value),
                        "memo": memo or "",
                        "created_at": now,
                        "updated_at": now,
                    }
                )
                existing.add(day)
                created += 1
            if created:
                self._flush()
        return created

    def count_points(self) -> int:
        with self._lock:
            return len(self._state["data"])

    # --------------------------------------------------------- conversations
    def list_conversations(self, limit: int, offset: int) -> tuple[list[dict], int]:
        with self._lock:
            items = [dict(item) for item in self._state["conversations"]]
        items.sort(key=lambda item: str(item.get("updated_at", "")), reverse=True)
        total = len(items)
        window = items[offset : offset + limit]
        return [conversation_summary(item) for item in window], total

    def get_conversation(self, conversation_id: str) -> dict | None:
        with self._lock:
            for item in self._state["conversations"]:
                if item["id"] == conversation_id:
                    return json.loads(json.dumps(item))
        return None

    def create_conversation(
        self, title: str, messages: list[dict], model: str | None = None
    ) -> dict:
        now = utcnow_iso()
        record = {
            "id": new_id(),
            "title": title,
            "messages": [normalize_message(message) for message in messages],
            "model": model,
            "created_at": now,
            "updated_at": now,
        }
        with self._lock:
            self._state["conversations"].append(record)
            self._flush()
        return json.loads(json.dumps(record))

    def append_messages(
        self, conversation_id: str, messages: list[dict], model: str | None = None
    ) -> dict | None:
        with self._lock:
            for item in self._state["conversations"]:
                if item["id"] == conversation_id:
                    item["messages"].extend(normalize_message(message) for message in messages)
                    item["updated_at"] = utcnow_iso()
                    if model:
                        item["model"] = model
                    self._flush()
                    return json.loads(json.dumps(item))
        return None

    def rename_conversation(self, conversation_id: str, title: str) -> dict | None:
        with self._lock:
            for item in self._state["conversations"]:
                if item["id"] == conversation_id:
                    item["title"] = title
                    item["updated_at"] = utcnow_iso()
                    self._flush()
                    return json.loads(json.dumps(item))
        return None

    def delete_conversation(self, conversation_id: str) -> bool:
        with self._lock:
            before = len(self._state["conversations"])
            self._state["conversations"] = [
                item for item in self._state["conversations"] if item["id"] != conversation_id
            ]
            deleted = len(self._state["conversations"]) != before
            if deleted:
                self._flush()
            return deleted

    def count_conversations(self) -> int:
        with self._lock:
            return len(self._state["conversations"])
