"""저장소 팩토리.

STORAGE_BACKEND=auto(기본)이면 Firebase 자격 증명 존재 여부에 따라
Firestore → 로컬 JSON 순서로 선택한다.
"""

from __future__ import annotations

import logging
import threading

from app.core.config import Settings, get_settings, parse_service_account
from app.repositories.base import Store
from app.repositories.firestore_store import FirestoreStore
from app.repositories.local_store import LocalStore

logger = logging.getLogger(__name__)

_store: Store | None = None
_lock = threading.Lock()


def build_store(settings: Settings | None = None) -> Store:
    settings = settings or get_settings()
    if settings.effective_storage == "firestore":
        raw = settings.firebase_credentials_source
        try:
            service_account = parse_service_account(raw or "")
            project_id = settings.firebase_project_id or service_account.get("project_id")
            store = FirestoreStore(service_account, project_id)
            logger.info("Firestore 저장소를 사용합니다. (project=%s)", project_id)
            return store
        except Exception as exc:  # 초기화 실패 시 로컬 폴백
            if settings.storage_backend == "firestore":
                raise
            logger.warning("Firestore 초기화 실패 → 로컬 저장소로 대체합니다: %s", exc)
    store = LocalStore(settings.local_store_dir)
    logger.info("로컬 JSON 저장소를 사용합니다. (%s)", settings.local_store_dir)
    return store


def get_store() -> Store:
    global _store
    if _store is None:
        with _lock:
            if _store is None:
                _store = build_store()
    return _store


def reset_store() -> None:
    """테스트에서 저장소를 교체할 때 사용한다."""
    global _store
    with _lock:
        _store = None
