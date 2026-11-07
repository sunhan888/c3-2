"""테스트 공통 설정.

실제 Firestore/OpenAI 없이도 전체 API를 검증할 수 있도록
로컬 저장소 + 빈 OpenAI 키(데모 폴백)로 앱을 띄운다.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

REPO_DIR = Path(__file__).resolve().parents[2]

# app.core.config가 import되기 전에 환경 변수를 확정한다.
os.environ["STORAGE_BACKEND"] = "local"
os.environ["LOCAL_STORE_DIR"] = tempfile.mkdtemp(prefix="datamate-test-")
os.environ["SEED_CSV_PATH"] = str(REPO_DIR / "data" / "seed_data.csv")
os.environ["SEED_ON_STARTUP"] = "true"
os.environ["OPENAI_API_KEY"] = ""
os.environ["DEMO_FALLBACK"] = "true"
os.environ["ALLOWED_ORIGINS"] = "*"


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
