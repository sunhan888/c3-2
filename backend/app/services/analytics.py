"""시계열 분석 서비스.

원본 데이터 포인트 목록만 있으면 되므로 저장소/프레임워크에 의존하지 않는다.
(`/api/data/summary`, `/api/data/statistics`, 채팅 컨텍스트 주입에서 공통 사용`)
"""

from __future__ import annotations

import statistics
from datetime import date, datetime, timedelta, timezone
from typing import Iterable, Sequence

WEEKDAY_LABELS = ["월", "화", "수", "목", "금", "토", "일"]
TREND_THRESHOLD = 1.0  # ±1% 미만이면 '유지'


def _to_date(value: object) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


def _sorted_points(points: Iterable[dict]) -> list[dict]:
    prepared = []
    for point in points:
        day = _to_date(point.get("date"))
        if day is None:
            continue
        try:
            value = float(point.get("value"))
        except (TypeError, ValueError):
            continue
        prepared.append(
            {
                "date": day,
                "value": value,
                "memo": str(point.get("memo") or ""),
                "id": str(point.get("id") or ""),
                "created_at": point.get("created_at"),
                "updated_at": point.get("updated_at"),
            }
        )
    prepared.sort(key=lambda item: (item["date"], item["id"]))
    return prepared


def _pct_change(current: float, previous: float) -> float:
    if previous == 0:
        return 0.0
    return round((current - previous) / previous * 100, 1)


def _trend_direction(change_pct: float) -> str:
    if change_pct >= TREND_THRESHOLD:
        return "상승"
    if change_pct <= -TREND_THRESHOLD:
        return "하락"
    return "유지"


def build_summary(
    points: Sequence[dict],
    *,
    topic: str = "시계열 데이터",
    unit: str = "원",
    window_days: int = 30,
    recent_days: int = 7,
) -> dict:
    """기간/개수/기본 통계/최근 트렌드를 담은 요약 정보를 만든다."""
    series = _sorted_points(points)
    generated_at = datetime.now(timezone.utc)
    if not series:
        return {
            "topic": topic,
            "unit": unit,
            "period": None,
            "count": 0,
            "metrics": None,
            "trend": None,
            "extremes": None,
            "recent": [],
            "generated_at": generated_at,
            "empty": True,
        }

    values = [item["value"] for item in series]
    start, end = series[0]["date"], series[-1]["date"]
    best = max(series, key=lambda item: item["value"])
    worst = min(series, key=lambda item: item["value"])

    window_days = max(2, min(window_days, max(2, len(series) // 2) or 2))
    recent_window = values[-window_days:]
    previous_window = values[-2 * window_days : -window_days]
    if previous_window:
        recent_avg = sum(recent_window) / len(recent_window)
        previous_avg = sum(previous_window) / len(previous_window)
    else:  # 데이터가 너무 적으면 앞/뒤 절반으로 비교
        half = max(1, len(values) // 2)
        recent_avg = sum(values[-half:]) / half
        previous_avg = sum(values[:half]) / half
        window_days = half
    change_pct = _pct_change(recent_avg, previous_avg)
    direction = _trend_direction(change_pct)
    sign = "+" if change_pct >= 0 else ""

    return {
        "topic": topic,
        "unit": unit,
        "period": {
            "start": start,
            "end": end,
            "label": f"{start.isoformat()} ~ {end.isoformat()}",
            "days": (end - start).days + 1,
        },
        "count": len(series),
        "metrics": {
            "total": round(sum(values)),
            "average": round(sum(values) / len(values)),
            "max": round(best["value"]),
            "min": round(worst["value"]),
            "median": round(statistics.median(values)),
            "latest": round(values[-1]),
        },
        "trend": {
            "direction": direction,
            "change_pct": change_pct,
            "window_days": window_days,
            "label": f"{direction} (최근 {window_days}일 일평균 {sign}{change_pct}%)",
            "recent_average": round(recent_avg),
            "previous_average": round(previous_avg),
        },
        "extremes": {
            "best": {
                "date": best["date"],
                "value": round(best["value"]),
                "memo": best["memo"],
            },
            "worst": {
                "date": worst["date"],
                "value": round(worst["value"]),
                "memo": worst["memo"],
            },
        },
        "recent": [
            {"date": item["date"], "value": round(item["value"])}
            for item in series[-max(1, recent_days) :]
        ],
        "generated_at": generated_at,
        "empty": False,
    }


def _month_key(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


def build_statistics(points: Sequence[dict], *, topic: str, unit: str, months: int = 12) -> dict:
    """시각화/인사이트용 확장 통계(월별, 요일별, 변동성, 이동평균)."""
    series = _sorted_points(points)
    generated_at = datetime.now(timezone.utc)
    if not series:
        return {
            "topic": topic,
            "unit": unit,
            "count": 0,
            "monthly": [],
            "weekday": [],
            "weekend_vs_weekday": {},
            "volatility": {"std_dev": 0.0, "coefficient_of_variation": 0.0},
            "growth": {"last_7_avg": 0.0, "prev_7_avg": 0.0, "change_pct": 0.0},
            "moving_average": [],
            "top_months": [],
            "generated_at": generated_at,
        }

    values = [item["value"] for item in series]
    overall_avg = sum(values) / len(values)

    # 월별 집계
    monthly_buckets: dict[str, list[float]] = {}
    for item in series:
        monthly_buckets.setdefault(_month_key(item["date"]), []).append(item["value"])
    monthly: list[dict] = []
    previous_avg: float | None = None
    for month in sorted(monthly_buckets):
        bucket = monthly_buckets[month]
        avg = sum(bucket) / len(bucket)
        monthly.append(
            {
                "month": month,
                "count": len(bucket),
                "total": round(sum(bucket)),
                "average": round(avg),
                "change_pct": None if previous_avg is None else _pct_change(avg, previous_avg),
            }
        )
        previous_avg = avg
    if months and len(monthly) > months:
        monthly = monthly[-months:]

    # 요일별 집계
    weekday_buckets: dict[int, list[float]] = {index: [] for index in range(7)}
    for item in series:
        weekday_buckets[item["date"].weekday()].append(item["value"])
    weekday_stats = []
    for index in range(7):
        bucket = weekday_buckets[index]
        avg = sum(bucket) / len(bucket) if bucket else 0.0
        weekday_stats.append(
            {
                "weekday": WEEKDAY_LABELS[index],
                "count": len(bucket),
                "average": round(avg),
                "index": round(avg / overall_avg, 3) if overall_avg else 0.0,
            }
        )

    weekend_values = weekday_buckets[5] + weekday_buckets[6]
    weekday_values = [value for index in range(5) for value in weekday_buckets[index]]
    weekday_avg = sum(weekday_values) / len(weekday_values) if weekday_values else 0.0
    weekend_avg = sum(weekend_values) / len(weekend_values) if weekend_values else 0.0

    std_dev = statistics.pstdev(values) if len(values) > 1 else 0.0
    last_7 = values[-7:]
    prev_7 = values[-14:-7] if len(values) >= 14 else values[: max(1, len(values) // 2)]
    last_7_avg = sum(last_7) / len(last_7)
    prev_7_avg = sum(prev_7) / len(prev_7) if prev_7 else 0.0

    # 7일 이동평균 (최근 30개 지점)
    moving_average = []
    for index, item in enumerate(series):
        window = values[max(0, index - 6) : index + 1]
        moving_average.append(
            {
                "date": item["date"],
                "value": round(item["value"]),
                "ma7": round(sum(window) / len(window)),
            }
        )
    moving_average = moving_average[-30:]

    top_months = sorted(monthly, key=lambda item: item["average"], reverse=True)[:3]

    return {
        "topic": topic,
        "unit": unit,
        "count": len(series),
        "monthly": monthly,
        "weekday": weekday_stats,
        "weekend_vs_weekday": {
            "weekday_average": round(weekday_avg),
            "weekend_average": round(weekend_avg),
            "gap_pct": _pct_change(weekend_avg, weekday_avg),
        },
        "volatility": {
            "std_dev": round(std_dev),
            "coefficient_of_variation": round(std_dev / overall_avg * 100, 1) if overall_avg else 0.0,
        },
        "growth": {
            "last_7_avg": round(last_7_avg),
            "prev_7_avg": round(prev_7_avg),
            "change_pct": _pct_change(last_7_avg, prev_7_avg),
        },
        "moving_average": moving_average,
        "top_months": top_months,
        "generated_at": generated_at,
    }


def describe_context(summary: dict) -> str:
    """UI/응답에 표시할 한 줄 컨텍스트 설명."""
    if summary.get("empty"):
        return "저장된 데이터가 없습니다."
    period = summary["period"]
    return (
        f"{summary['count']}개 레코드 · {period['label']} · {summary['trend']['label']}"
    )


def filter_points(
    points: Sequence[dict], start: date | None, end: date | None
) -> list[dict]:
    series = _sorted_points(points)
    if start:
        series = [item for item in series if item["date"] >= start]
    if end:
        series = [item for item in series if item["date"] <= end]
    return series


def date_range_label(days: int) -> str:
    today = date.today()
    return f"{(today - timedelta(days=days)).isoformat()} ~ {today.isoformat()}"
