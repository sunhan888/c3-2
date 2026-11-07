"""로컬 실행 진입점.

    uvicorn main:app --reload --port 8000

`app` 패키지의 팩토리에서 FastAPI 인스턴스를 가져온다.
"""

from __future__ import annotations

from app.main import app

__all__ = ["app"]


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
