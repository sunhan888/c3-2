"""채팅 오케스트레이션.

흐름: 데이터 요약 계산 → 시스템 프롬프트 주입 → (필요 시 도구 호출) → GPT 호출
      → 대화 저장(자동) → 응답 반환
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from fastapi import HTTPException, status

from app.core.config import Settings
from app.models.schemas import ChatRequest
from app.repositories.base import Store
from app.services.ai_service import AIResult, AIService, AIServiceError, build_tool_schemas
from app.services.analytics import build_statistics, build_summary, describe_context, filter_points
from app.services.demo_responder import generate_demo_answer
from app.services.prompts import build_system_prompt

logger = logging.getLogger(__name__)


def make_title(message: str, limit: int = 34) -> str:
    single_line = " ".join(message.split())
    return single_line[:limit] + ("…" if len(single_line) > limit else "")


class ChatService:
    def __init__(self, store: Store, settings: Settings) -> None:
        self.store = store
        self.settings = settings
        self.ai = AIService(settings)

    # ------------------------------------------------------------------ context
    def build_context(self) -> tuple[dict, dict]:
        points = self.store.list_points()
        summary = build_summary(
            points,
            topic=self.settings.data_topic,
            unit=self.settings.data_unit,
            window_days=self.settings.trend_window_days,
            recent_days=self.settings.recent_days,
        )
        statistics = build_statistics(
            points,
            topic=self.settings.data_topic,
            unit=self.settings.data_unit,
        )
        return summary, statistics

    def _tool_executors(self) -> dict:
        def get_data_summary(_: dict) -> tuple[dict, str]:
            summary, _stats = self.build_context()
            if summary.get("empty"):
                return summary, "데이터 없음"
            return summary, f"{summary['count']}개 레코드 요약"

        def get_data_statistics(_: dict) -> tuple[dict, str]:
            _summary, statistics = self.build_context()
            return statistics, f"월별 {len(statistics['monthly'])}개 / 요일 7개 통계"

        def get_data_points(arguments: dict) -> tuple[dict, str]:
            start = _parse_day(arguments.get("start_date"))
            end = _parse_day(arguments.get("end_date"))
            limit = int(arguments.get("limit") or 20)
            limit = max(1, min(limit, 60))
            points = filter_points(self.store.list_points(), start, end)[-limit:]
            payload = {
                "count": len(points),
                "points": [
                    {"date": item["date"].isoformat(), "value": round(item["value"]), "memo": item["memo"]}
                    for item in points
                ],
            }
            return payload, f"{len(points)}개 포인트 조회"

        def list_recent_conversations(arguments: dict) -> tuple[dict, str]:
            limit = int(arguments.get("limit") or 5)
            limit = max(1, min(limit, 10))
            items, total = self.store.list_conversations(limit=limit, offset=0)
            return {"total": total, "items": items}, f"대화 {len(items)}건 조회"

        return {
            "get_data_summary": get_data_summary,
            "get_data_statistics": get_data_statistics,
            "get_data_points": get_data_points,
            "list_recent_conversations": list_recent_conversations,
        }

    # ------------------------------------------------------------------ chat
    def chat(self, request: ChatRequest) -> dict:
        conversation = None
        if request.conversation_id:
            conversation = self.store.get_conversation(request.conversation_id)
            if conversation is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"code": "conversation_not_found", "message": "해당 대화를 찾을 수 없습니다."},
                )

        summary, statistics = self.build_context()
        system_prompt = build_system_prompt(summary, statistics)

        history: list[dict] = []
        if conversation:
            history = [
                {"role": item.get("role", "user"), "content": item.get("content", "")}
                for item in conversation.get("messages", [])
                if item.get("role") in {"user", "assistant"}
            ][-self.settings.openai_history_limit :]

        messages = [{"role": "system", "content": system_prompt}, *history, {"role": "user", "content": request.message}]

        executors = self._tool_executors()
        try:
            result = self.ai.complete(
                messages,
                tool_executor=lambda name, args: executors[name](args),
                tools=build_tool_schemas() if self.settings.tools_enabled else None,
            )
        except AIServiceError as exc:
            logger.warning("AI 응답 실패: %s", exc.message)
            if exc.status_code == 503 and self.settings.demo_fallback:
                # LLM 키가 없는 시연용 배포: 데이터 요약 기반 규칙 응답으로 대체
                result = AIResult(
                    content=generate_demo_answer(request.message, summary, statistics),
                    model="demo-rule-based",
                    tool_calls=[],
                    latency_ms=0,
                )
            else:
                raise HTTPException(
                    status_code=exc.status_code,
                    detail={"code": "llm_error", "message": exc.message},
                ) from exc

        reply = result.content
        now = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        new_messages = [
            {"role": "user", "content": request.message, "created_at": now},
            {"role": "assistant", "content": reply, "created_at": now},
        ]

        saved_conversation = None
        if request.save:
            if conversation:
                saved_conversation = self.store.append_messages(
                    conversation["id"], new_messages, model=result.model
                )
                if saved_conversation is None:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail={"code": "conversation_not_found", "message": "해당 대화를 찾을 수 없습니다."},
                    )
            else:
                saved_conversation = self.store.create_conversation(
                    title=make_title(request.message), messages=new_messages, model=result.model
                )

        response_messages = (
            saved_conversation["messages"] if saved_conversation else new_messages
        )

        return {
            "conversation_id": (saved_conversation or {}).get("id", request.conversation_id or ""),
            "reply": reply,
            "messages": response_messages,
            "model": result.model,
            "used_tools": result.tool_calls,
            "latency_ms": result.latency_ms,
            "saved": bool(saved_conversation),
            "summary": summary,
            "context_note": describe_context(summary),
        }


def _parse_day(value: object) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None
