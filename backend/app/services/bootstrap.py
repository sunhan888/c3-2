"""시작 시 시드 데이터 보장.

저장소가 비어 있을 때만 CSV(또는 내장 시드)를 적재한다.
덕분에 첫 배포 직후에도 365일치 데이터로 바로 질문할 수 있다.
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path

from app.core.config import Settings
from app.repositories.base import Store

logger = logging.getLogger(__name__)


def load_seed_rows(path: Path) -> list[tuple[str, float, str]]:
    if path.exists():
        rows: list[tuple[str, float, str]] = []
        with path.open(encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                try:
                    rows.append((row["date"], float(row["value"]), row.get("memo") or ""))
                except (KeyError, TypeError, ValueError):
                    continue
        if rows:
            return rows
    # 파일이 번들에 포함되지 않는 환경(Vercel 등)을 위한 내장 사본
    from app.data.seed_rows import SEED_ROWS

    return list(SEED_ROWS)


def ensure_seed_data(store: Store, settings: Settings) -> int:
    if not settings.seed_on_startup:
        return 0
    if store.count_points() > 0:
        return 0
    try:
        rows = load_seed_rows(settings.seed_csv)
        created = store.bulk_add_points(rows)
        logger.info("시드 데이터 %s건을 적재했습니다.", created)
        return created
    except Exception as exc:  # 시드 실패가 서비스 기동을 막지 않도록
        logger.warning("시드 데이터 적재 실패: %s", exc)
        return 0
