"""시드 데이터 생성 스크립트.

'1인 스터디카페'의 일별 매출(원) 365일치를 결정론적으로 생성한다.
- 요일 효과(주말 매출 상승), 월별 계절성(시험 기간/방학), 완만한 성장 추세,
  프로모션/공휴일 이벤트를 반영해 실제 운영 데이터와 유사한 형태를 만든다.
- 같은 시드로 항상 같은 결과가 나오므로 재현 가능하다.

사용법:
    python scripts/generate_seed.py            # data/seed_data.csv 생성
    python scripts/generate_seed.py --check    # 요약 통계만 출력
"""

from __future__ import annotations

import argparse
import csv
import random
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent
CSV_PATH = REPO_DIR / "data" / "seed_data.csv"

START = date(2025, 11, 7)
DAYS = 365
BASE_REVENUE = 430_000  # 평일 기준 일 매출(원)

# 월별 계절성: 1~2월 방학/비수기, 4~6월·9~12월 시험 기간 성수기
MONTH_FACTOR = {
    1: 0.94,
    2: 0.97,
    3: 1.04,
    4: 1.09,
    5: 1.05,
    6: 1.11,
    7: 0.91,
    8: 0.89,
    9: 1.07,
    10: 1.10,
    11: 1.13,
    12: 1.16,
}

# 요일 효과 (월=0 ... 일=6)
WEEKDAY_FACTOR = [0.94, 0.96, 1.00, 1.02, 1.09, 1.24, 1.16]

# 특별 이벤트: (날짜, 배수, 메모)
EVENTS = {
    date(2025, 12, 24): (0.72, "크리스마스 이브 단축 운영"),
    date(2025, 12, 31): (1.35, "연말 심야 특수"),
    date(2026, 1, 1): (0.55, "신정 휴무"),
    date(2026, 2, 16): (0.60, "설 연휴"),
    date(2026, 2, 17): (0.58, "설 연휴"),
    date(2026, 3, 2): (1.32, "신학기 1+1 프로모션"),
    date(2026, 4, 20): (1.28, "중간고사 기간 특수"),
    date(2026, 6, 8): (1.30, "기말고사 기간 특수"),
    date(2026, 7, 20): (0.70, "여름 방학 비수기"),
    date(2026, 9, 1): (1.25, "2학기 개강 프로모션"),
    date(2026, 9, 24): (0.62, "추석 연휴"),
    date(2026, 9, 25): (0.60, "추석 연휴"),
    date(2026, 10, 19): (1.22, "중간고사 기간 특수"),
    date(2026, 11, 2): (1.30, "11월 야간권 프로모션"),
    date(2026, 11, 5): (1.18, "수능 D-14 특수"),
}


def build_rows() -> list[dict[str, object]]:
    rng = random.Random(20261107)
    rows: list[dict[str, object]] = []
    for index in range(DAYS):
        day = START + timedelta(days=index)
        growth = (1.0 + 0.00055) ** index  # 연간 약 +22% 완만한 성장
        multiplier = MONTH_FACTOR[day.month] * WEEKDAY_FACTOR[day.weekday()] * growth
        noise = rng.gauss(1.0, 0.055)
        value = BASE_REVENUE * multiplier * noise
        memo = ""
        if day in EVENTS:
            factor, memo = EVENTS[day]
            value *= factor
        elif day.weekday() >= 5 and rng.random() < 0.18:
            memo = "주말 단체 예약"
        elif rng.random() < 0.06:
            memo = "인근 대학 행사"
        value = max(120_000, round(value / 1000) * 1000)
        rows.append({"date": day.isoformat(), "value": value, "memo": memo})
    return rows


def write_csv(rows: list[dict[str, object]]) -> None:
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CSV_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["date", "value", "memo"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"저장 완료: {CSV_PATH} ({len(rows)}개 레코드)")


def print_check(rows: list[dict[str, object]]) -> None:
    values = [int(row["value"]) for row in rows]
    total = sum(values)
    avg = total / len(values)
    recent = values[-30:]
    previous = values[-60:-30]
    change = (sum(recent) / 30 - sum(previous) / 30) / (sum(previous) / 30) * 100
    best = max(rows, key=lambda row: int(row["value"]))
    worst = min(rows, key=lambda row: int(row["value"]))
    by_month: dict[str, list[int]] = defaultdict(list)
    for row in rows:
        by_month[str(row["date"])[:7]].append(int(row["value"]))
    print(f"기간: {rows[0]['date']} ~ {rows[-1]['date']} ({len(rows)}일)")
    print(f"총매출: {total:,}원 / 일평균: {avg:,.0f}원")
    print(f"최고: {best['date']} {int(best['value']):,}원 / 최저: {worst['date']} {int(worst['value']):,}원")
    print(f"최근 30일 트렌드: {change:+.1f}%")
    print("월별 평균:", {month: f"{sum(vals) / len(vals):,.0f}" for month, vals in sorted(by_month.items())})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="스터디카페 일별 매출 시드 데이터 생성")
    parser.add_argument("--check", action="store_true", help="CSV를 쓰지 않고 통계만 확인")
    args = parser.parse_args()
    data = build_rows()
    if not args.check:
        write_csv(data)
    print_check(data)
