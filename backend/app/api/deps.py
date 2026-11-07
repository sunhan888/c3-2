"""FastAPI 의존성."""

from __future__ import annotations

from fastapi import Depends

from app.core.config import Settings, get_settings
from app.repositories.base import Store
from app.repositories.factory import get_store


def store_dependency() -> Store:
    return get_store()


def settings_dependency() -> Settings:
    return get_settings()


StoreDep = Depends(store_dependency)
SettingsDep = Depends(settings_dependency)
