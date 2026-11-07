"""Vercel Python 함수 진입점 (백엔드 데모 배포용).

Render 배포가 기본이지만, 동일한 FastAPI 앱을 Vercel 서버리스로도 띄울 수 있도록
ASGI 앱을 그대로 노출한다.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import app  # noqa: E402

__all__ = ["app"]
