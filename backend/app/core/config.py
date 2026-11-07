"""애플리케이션 설정.

민감 정보(OpenAI 키, Firebase 서비스 계정)는 코드에 하드코딩하지 않고
환경 변수 또는 `.env` 파일에서만 읽는다.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = BACKEND_DIR.parent

# 로컬 개발 편의를 위해 저장소 루트와 backend 디렉터리의 .env를 모두 읽는다.
for _candidate in (REPO_DIR / ".env", BACKEND_DIR / ".env"):
    if _candidate.exists():
        load_dotenv(_candidate, override=False)

TRUE_VALUES = {"1", "true", "yes", "on", "y"}


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in TRUE_VALUES


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_origins() -> tuple[str, ...]:
    raw = os.getenv("ALLOWED_ORIGINS", "").strip()
    if not raw:
        return ("*",)
    origins = tuple(item.strip().rstrip("/") for item in raw.split(",") if item.strip())
    return origins or ("*",)


def _env_path(name: str, default: Path) -> Path:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    path = Path(raw)
    return path if path.is_absolute() else (BACKEND_DIR / path).resolve()


@dataclass(frozen=True)
class Settings:
    """환경 변수 기반 설정 스냅샷."""

    app_name: str = "DataMate API"
    app_version: str = "1.0.0"

    # CORS
    allowed_origins: tuple[str, ...] = field(default_factory=_env_origins)

    # 저장소
    storage_backend: str = "auto"  # auto | firestore | local
    firebase_service_account_json: str | None = None
    firebase_credentials_path: str | None = None
    firebase_project_id: str | None = None
    local_store_dir: Path = BACKEND_DIR / ".local_store"
    seed_csv: Path = REPO_DIR / "data" / "seed_data.csv"
    seed_on_startup: bool = True
    data_topic: str = "1인 스터디카페 일별 매출"
    data_unit: str = "원"

    # LLM
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    openai_model: str = "gpt-4o-mini"
    openai_max_tokens: int = 700
    openai_temperature: float = 0.3
    openai_history_limit: int = 12
    openai_timeout: float = 60.0
    enable_tools: bool = True
    # LLM 키가 없는 시연용 배포에서 규칙 기반 응답을 사용할지 여부
    demo_fallback: bool = False

    # 요약 파라미터
    trend_window_days: int = 30
    recent_days: int = 7

    # 프론트엔드 정적 서빙(로컬 편의 기능)
    serve_frontend: bool = True
    frontend_dir: Path = REPO_DIR / "frontend"

    @property
    def firebase_credentials_source(self) -> str | None:
        """서비스 계정 JSON(문자열) 또는 파일 경로를 반환한다."""
        if self.firebase_service_account_json:
            return self.firebase_service_account_json
        if self.firebase_credentials_path:
            return self.firebase_credentials_path
        return os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or None

    @property
    def effective_storage(self) -> str:
        if self.storage_backend == "firestore":
            return "firestore"
        if self.storage_backend == "local":
            return "local"
        return "firestore" if self.firebase_credentials_source else "local"

    @property
    def tools_enabled(self) -> bool:
        return self.enable_tools and bool(self.openai_api_key)

    @classmethod
    def load(cls) -> "Settings":
        return cls(
            app_name=os.getenv("APP_NAME", "DataMate API"),
            app_version=os.getenv("APP_VERSION", "1.0.0"),
            allowed_origins=_env_origins(),
            storage_backend=os.getenv("STORAGE_BACKEND", "auto").strip().lower(),
            firebase_service_account_json=os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON") or None,
            firebase_credentials_path=os.getenv("FIREBASE_CREDENTIALS_PATH") or None,
            firebase_project_id=os.getenv("FIREBASE_PROJECT_ID") or None,
            local_store_dir=_env_path("LOCAL_STORE_DIR", BACKEND_DIR / ".local_store"),
            seed_csv=_env_path("SEED_CSV_PATH", REPO_DIR / "data" / "seed_data.csv"),
            seed_on_startup=_env_bool("SEED_ON_STARTUP", True),
            data_topic=os.getenv("DATA_TOPIC", "1인 스터디카페 일별 매출"),
            data_unit=os.getenv("DATA_UNIT", "원"),
            openai_api_key=os.getenv("OPENAI_API_KEY") or None,
            openai_base_url=os.getenv("OPENAI_BASE_URL") or None,
            openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            openai_max_tokens=_env_int("OPENAI_MAX_TOKENS", 700),
            openai_temperature=_env_float("OPENAI_TEMPERATURE", 0.3),
            openai_history_limit=_env_int("OPENAI_HISTORY_LIMIT", 12),
            openai_timeout=_env_float("OPENAI_TIMEOUT", 60.0),
            enable_tools=_env_bool("ENABLE_TOOLS", True),
            demo_fallback=_env_bool("DEMO_FALLBACK", False),
            trend_window_days=_env_int("TREND_WINDOW_DAYS", 30),
            recent_days=_env_int("RECENT_DAYS", 7),
            serve_frontend=_env_bool("SERVE_FRONTEND", True),
            frontend_dir=_env_path("FRONTEND_DIR", REPO_DIR / "frontend"),
        )

    def public_snapshot(self) -> dict[str, object]:
        """README/헬스체크용 비민감 설정 요약."""
        return {
            "app_name": self.app_name,
            "app_version": self.app_version,
            "storage_backend": self.effective_storage,
            "model": self.openai_model,
            "tools_enabled": self.tools_enabled,
            "demo_fallback": self.demo_fallback,
            "allowed_origins": list(self.allowed_origins),
            "data_topic": self.data_topic,
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.load()


def reset_settings_cache() -> None:
    """테스트에서 환경 변수를 바꾼 뒤 설정을 다시 읽을 때 사용한다."""
    get_settings.cache_clear()


def parse_service_account(raw: str) -> dict:
    """서비스 계정 JSON 문자열 또는 파일 경로를 dict로 변환한다."""
    candidate = Path(raw)
    if candidate.exists():
        return json.loads(candidate.read_text(encoding="utf-8"))
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:  # pragma: no cover - 운영 실수 방어
        raise ValueError(
            "FIREBASE_SERVICE_ACCOUNT_JSON 값이 JSON 문자열도, 파일 경로도 아닙니다."
        ) from exc
