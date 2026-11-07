"""LLM 키가 없는 데모 배포용 규칙 기반 응답기.

주의: 이 모듈은 "AI 답변"이 아니라, 화면 동작을 확인할 수 있도록 만든 안전장치다.
실제 서비스에서는 반드시 OPENAI_API_KEY를 설정해 GPT 응답을 사용한다.
(응답 끝에 데모임을 명시하고, 프론트엔드도 DEMO 배지를 표시한다)
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

SEOUL = ZoneInfo("Asia/Seoul")
FOOTER = "\n\n※ 이 응답은 데모 모드(OPENAI_API_KEY 미설정)에서 규칙 기반으로 생성되었습니다."


def _won(value: float) -> str:
    return f"{int(round(value)):,}원"


def generate_demo_answer(message: str, summary: dict, statistics: dict | None = None) -> str:
    if not summary or summary.get("empty"):
        return "아직 저장된 데이터가 없어요. '데이터 관리' 탭에서 날짜와 매출을 추가하면 분석을 시작할 수 있어요." + FOOTER

    metrics = summary["metrics"]
    trend = summary["trend"]
    best = summary["extremes"]["best"]
    worst = summary["extremes"]["worst"]
    period = summary["period"]
    weekend = (statistics or {}).get("weekend_vs_weekday") or {}
    monthly = (statistics or {}).get("monthly") or []
    text = (message or "").lower()

    if any(word in message for word in ("최고", "가장 좋", "최대", "베스트")):
        memo = f" 당시 메모는 '{best['memo']}'였어요." if best.get("memo") else ""
        return (
            f"전체 기간({period['label']})에서 가장 매출이 좋았던 날은 **{best['date']}**로 "
            f"**{_won(best['value'])}**을 기록했어요.{memo} 일평균({_won(metrics['average'])})보다 "
            f"{best['value'] / metrics['average'] * 100 - 100:+.1f}% 높은 수준입니다."
            + FOOTER
        )

    if any(word in message for word in ("최저", "가장 나쁜", "최소", "부진")):
        memo = f" 메모는 '{worst['memo']}'였어요." if worst.get("memo") else ""
        return (
            f"가장 매출이 낮았던 날은 **{worst['date']}**의 **{_won(worst['value'])}**예요.{memo} "
            f"일평균 대비 {worst['value'] / metrics['average'] * 100 - 100:+.1f}% 수준입니다."
            + FOOTER
        )

    if any(word in message for word in ("주말", "주중", "요일")):
        if weekend:
            return (
                f"주말 평균은 **{_won(weekend.get('weekend_average', 0))}**, 주중 평균은 "
                f"**{_won(weekend.get('weekday_average', 0))}**으로 주말이 "
                f"**{weekend.get('gap_pct', 0):+.1f}%** 높아요. 토요일이 가장 강한 요일입니다."
                + FOOTER
            )
        return "요일별 통계를 계산할 데이터가 부족해요." + FOOTER

    if any(word in message for word in ("추세", "트렌드", "요즘", "최근")):
        return (
            f"최근 {trend['window_days']}일 일평균은 **{_won(trend['recent_average'])}**으로 직전 동일 구간"
            f"({_won(trend['previous_average'])})보다 **{trend['change_pct']:+.1f}%** 변동했어요. "
            f"현재 추세는 **{trend['direction']}**입니다."
            + FOOTER
        )

    if "이번 달" in message:
        today = datetime.now(SEOUL)
        current_key = f"{today.year:04d}-{today.month:02d}"
        current = next((row for row in reversed(monthly) if row["month"] == current_key), None)
        if current:
            previous = next(
                (row for row in reversed(monthly) if row["month"] < current_key), None
            )
            comparison = ""
            if previous:
                gap = (current["average"] / previous["average"] - 1) * 100
                comparison = f" 전월({previous['month']}) 평균 {_won(previous['average'])} 대비 {gap:+.1f}% 수준이에요."
            return (
                f"이번 달({current_key}) 일평균은 **{_won(current['average'])}**이고 합계는 "
                f"**{_won(current['total'])}**입니다.{comparison}"
                + FOOTER
            )

    return (
        f"현재 데이터는 **{period['label']}** 기간의 **{summary['count']}건**이에요. "
        f"합계 {_won(metrics['total'])}, 일평균 {_won(metrics['average'])}, "
        f"최고 {_won(metrics['max'])}, 최저 {_won(metrics['min'])}이고 최근 추세는 **{trend['label']}**입니다. "
        f"'최고 매출일', '주말과 주중 차이', '최근 추세'처럼 구체적으로 물어보시면 자세히 알려드릴게요."
        + FOOTER
    )
