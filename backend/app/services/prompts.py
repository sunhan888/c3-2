"""시스템 프롬프트 구성.

핵심 아이디어는 '컨텍스트 주입'이다. 매 요청마다 데이터 요약을 계산해
시스템 프롬프트에 넣어 주면, 모델은 별도 파인튜닝 없이도 사용자의 실제 수치를
근거로 답변할 수 있다. (모델은 DB에 직접 접근하지 않는다)
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

SEOUL = ZoneInfo("Asia/Seoul")


def _money(value: float, unit: str) -> str:
    return f"{int(round(value)):,}{unit}"


def _format_recent(recent: list[dict], unit: str) -> str:
    if not recent:
        return "- 없음"
    return " / ".join(
        f"{item['date'].strftime('%m/%d')} {_money(item['value'], unit)}" for item in recent
    )


def _format_monthly(monthly: list[dict], unit: str, limit: int = 4) -> str:
    if not monthly:
        return "- 없음"
    rows = monthly[-limit:]
    return ", ".join(
        f"{row['month']} 평균 {_money(row['average'], unit)}"
        + (f"({row['change_pct']:+.1f}%)" if row.get("change_pct") is not None else "")
        for row in rows
    )


def _format_weekday(weekday: list[dict], unit: str) -> str:
    if not weekday:
        return "- 없음"
    return ", ".join(
        f"{row['weekday']} {_money(row['average'], unit)}" for row in weekday
    )


def build_system_prompt(summary: dict, statistics: dict | None = None) -> str:
    unit = summary.get("unit", "원")
    today = datetime.now(SEOUL)
    header = (
        "당신은 'DataMate'입니다. 사용자의 시계열 데이터를 근거로 답하는 데이터 분석 비서입니다.\n"
        f"오늘 날짜: {today.strftime('%Y-%m-%d')} ({today.strftime('%A')}, Asia/Seoul)\n"
    )

    if summary.get("empty"):
        return (
            header
            + "\n[사용자 데이터 요약]\n- 아직 저장된 데이터가 없습니다.\n"
            + "\n[답변 규칙]\n1. 데이터가 없다는 점을 먼저 알리고, 화면의 '데이터 관리' 탭에서 "
            "날짜/값/메모를 추가하면 분석을 시작할 수 있다고 안내하세요.\n2. 추측으로 수치를 만들어내지 마세요.\n"
        )

    period = summary["period"]
    metrics = summary["metrics"]
    trend = summary["trend"]
    best = summary["extremes"]["best"]
    worst = summary["extremes"]["worst"]

    lines = [
        header,
        "[사용자 데이터 요약]",
        f"- 데이터 주제: {summary['topic']} (단위: {unit})",
        f"- 데이터 기간: {period['label']} ({summary['count']}개 레코드, {period['days']}일)",
        f"- 합계: {_money(metrics['total'], unit)}",
        f"- 일평균: {_money(metrics['average'], unit)} / 중앙값: {_money(metrics['median'], unit)}",
        f"- 최고: {best['date'].isoformat()} {_money(best['value'], unit)}"
        + (f" ({best['memo']})" if best.get("memo") else ""),
        f"- 최저: {worst['date'].isoformat()} {_money(worst['value'], unit)}"
        + (f" ({worst['memo']})" if worst.get("memo") else ""),
        f"- 최근 트렌드: {trend['label']} (직전 {trend['window_days']}일 평균 "
        f"{_money(trend['previous_average'], unit)} → 최근 {_money(trend['recent_average'], unit)})",
        f"- 최근 {len(summary['recent'])}일: {_format_recent(summary['recent'], unit)}",
    ]

    if statistics:
        weekend = statistics.get("weekend_vs_weekday") or {}
        if weekend:
            lines.append(
                f"- 주말/주중: 주말 평균 {_money(weekend.get('weekend_average', 0), unit)} "
                f"(주중 대비 {weekend.get('gap_pct', 0):+.1f}%)"
            )
        lines.append(f"- 요일별 평균: {_format_weekday(statistics.get('weekday', []), unit)}")
        lines.append(f"- 월별 추이: {_format_monthly(statistics.get('monthly', []), unit)}")
        volatility = statistics.get("volatility") or {}
        if volatility:
            lines.append(f"- 변동성(표준편차): {_money(volatility.get('std_dev', 0), unit)}")

    lines.extend(
        [
            "",
            "[답변 규칙]",
            "1. 위 수치를 근거로 답하세요. 데이터에 없는 값(미래 예측, 외부 정보)은 '추정'임을 밝히고 근거를 함께 설명하세요.",
            "2. 금액은 천 단위 구분과 단위(원)를 붙이고, 변화율은 소수점 1자리까지 표기하세요.",
            "3. 기본은 3~4문장으로 간결하게, 목록이 더 명확할 때만 짧은 불릿을 사용하세요.",
            "4. 친근한 존댓말(~요 체)을 쓰고, 과장된 표현은 피하세요.",
            "5. 더 정확한 답을 위해 필요하면 제공된 도구(get_data_summary, get_data_statistics, "
            "get_data_points, list_recent_conversations)를 호출하세요.",
        ]
    )
    return "\n".join(lines)
