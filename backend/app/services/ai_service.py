"""OpenAI 호출 래퍼.

- 모델 계열(reasoning/non-reasoning)에 따라 토큰 옵션을 다르게 보낸다.
- Function Calling(도구 호출) 루프를 지원한다. (보너스 과제)
- API 키는 설정에서만 읽는다.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Callable

from openai import APIConnectionError, APIStatusError, OpenAI

from app.core.config import Settings

logger = logging.getLogger(__name__)

REASONING_PATTERN = re.compile(r"^(gpt-5|gpt-6|o[1-9])", re.IGNORECASE)
MAX_TOOL_ROUNDS = 3

ToolExecutor = Callable[[str, dict], tuple[dict, str]]


class AIServiceError(RuntimeError):
    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass
class AIResult:
    content: str
    model: str
    tool_calls: list[dict] = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    latency_ms: int = 0


def build_tool_schemas() -> list[dict]:
    """모델이 호출할 수 있는 내부 API 도구 정의(JSON Schema)."""
    return [
        {
            "type": "function",
            "function": {
                "name": "get_data_summary",
                "description": "저장된 시계열 데이터의 요약(기간, 개수, 합계/평균/최대/최소, 최근 트렌드)을 조회한다.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_data_statistics",
                "description": "월별/요일별 평균, 변동성, 최근 7일 성장률 등 확장 통계를 조회한다.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_data_points",
                "description": "특정 기간의 일별 데이터 포인트를 조회한다. 특정 날짜/구간을 콕 집어 물을 때 사용한다.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "start_date": {"type": "string", "description": "시작일 YYYY-MM-DD (선택)"},
                        "end_date": {"type": "string", "description": "종료일 YYYY-MM-DD (선택)"},
                        "limit": {
                            "type": "integer",
                            "description": "최대 반환 개수(기본 20, 최대 60)",
                            "minimum": 1,
                            "maximum": 60,
                        },
                    },
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_recent_conversations",
                "description": "이전 대화 기록 목록(제목, 마지막 갱신 시각, 메시지 수)을 조회한다. '지난번에 뭐 물어봤지?' 같은 질문에 사용한다.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5}
                    },
                    "required": [],
                },
            },
        },
    ]


class AIService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.model = settings.openai_model
        self._client: OpenAI | None = None
        if settings.openai_api_key:
            kwargs: dict = {"api_key": settings.openai_api_key, "timeout": settings.openai_timeout}
            if settings.openai_base_url:
                kwargs["base_url"] = settings.openai_base_url
            self._client = OpenAI(**kwargs)

    @property
    def available(self) -> bool:
        return self._client is not None

    def _is_reasoning(self, model: str) -> bool:
        return bool(REASONING_PATTERN.match(model))

    def _base_kwargs(self, token_budget: int | None = None) -> dict:
        """모델 계열에 맞는 토큰 옵션을 만든다.

        추론(reasoning) 모델은 내부 사고 토큰도 출력 토큰에 포함되므로
        일반 모델보다 넉넉한 예산을 잡아야 빈 응답이 나오지 않는다.
        """
        kwargs: dict = {"model": self.model}
        configured = token_budget or self.settings.openai_max_tokens
        if self._is_reasoning(self.model):
            kwargs["max_completion_tokens"] = max(configured * 4, 2500)
        else:
            kwargs["max_tokens"] = configured
            kwargs["temperature"] = self.settings.openai_temperature
        return kwargs

    def _create(self, conversation: list[dict], tools: list[dict] | None, token_budget: int | None = None):
        payload = self._base_kwargs(token_budget)
        if tools:
            payload.update({"tools": tools, "tool_choice": "auto"})
        return self._client.chat.completions.create(messages=conversation, **payload)

    def complete(
        self,
        messages: list[dict],
        tool_executor: ToolExecutor | None = None,
        tools: list[dict] | None = None,
    ) -> AIResult:
        if self._client is None:
            raise AIServiceError(
                "OpenAI API 키가 설정되지 않았습니다. OPENAI_API_KEY 환경 변수를 등록해 주세요.",
                status_code=503,
            )

        tool_calls_log: list[dict] = []
        conversation = list(messages)
        started = time.perf_counter()
        usage: dict = {}

        try:
            rounds = MAX_TOOL_ROUNDS if (tools and tool_executor) else 0
            budget_multiplier = 1
            for round_index in range(rounds + 1):
                use_tools = tools if (tools and tool_executor and round_index < rounds) else None
                response = self._create(conversation, use_tools, self.settings.openai_max_tokens * budget_multiplier)
                if getattr(response, "usage", None):
                    usage = response.usage.model_dump()
                choice = response.choices[0]
                message = choice.message

                if message.tool_calls and tool_executor and round_index < rounds:
                    conversation.append(
                        {
                            "role": "assistant",
                            "content": message.content or "",
                            "tool_calls": [call.model_dump() for call in message.tool_calls],
                        }
                    )
                    for call in message.tool_calls:
                        name = call.function.name
                        try:
                            arguments = json.loads(call.function.arguments or "{}")
                        except json.JSONDecodeError:
                            arguments = {}
                        try:
                            payload, summary = tool_executor(name, arguments)
                            tool_calls_log.append(
                                {"name": name, "arguments": arguments, "ok": True, "summary": summary}
                            )
                        except Exception as exc:  # 도구 실패가 전체 답변을 막지 않도록
                            logger.warning("도구 실행 실패: %s (%s)", name, exc)
                            payload = {"error": str(exc)}
                            tool_calls_log.append(
                                {"name": name, "arguments": arguments, "ok": False, "summary": "도구 실행 실패"}
                            )
                        conversation.append(
                            {
                                "role": "tool",
                                "tool_call_id": call.id,
                                "content": json.dumps(payload, ensure_ascii=False, default=str),
                            }
                        )
                    continue

                content = (message.content or "").strip()
                if not content and choice.finish_reason == "length" and budget_multiplier < 3:
                    # 사고 토큰이 예산을 모두 사용한 경우: 예산을 늘려 1회 재시도
                    logger.info("응답이 토큰 한도로 비었습니다. 예산을 늘려 재시도합니다.")
                    budget_multiplier += 1
                    continue
                if not content:
                    content = "죄송해요, 답변을 생성하지 못했어요. 질문을 조금 더 구체적으로 다시 말씀해 주시겠어요?"
                return AIResult(
                    content=content,
                    model=response.model or self.model,
                    tool_calls=tool_calls_log,
                    usage=usage,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                )
        except APIStatusError as exc:
            logger.error("OpenAI API 오류: %s %s", exc.status_code, exc.message)
            hint = ""
            if exc.status_code == 401:
                hint = " (API 키를 확인해 주세요)"
            elif exc.status_code == 429:
                hint = " (요청 한도/크레딧을 확인해 주세요)"
            raise AIServiceError(
                f"LLM 호출에 실패했습니다: {exc.message}{hint}", status_code=502
            ) from exc
        except APIConnectionError as exc:
            raise AIServiceError(
                "LLM 서버에 연결하지 못했습니다. 네트워크 또는 API 주소를 확인해 주세요.", status_code=502
            ) from exc

        # 도구 호출 루프가 끝까지 이어진 경우에도 사용자에게는 안내 문구를 돌려준다.
        return AIResult(
            content="답변을 준비하다가 요청이 길어졌어요. 질문을 조금 더 짧게 다시 보내 주시겠어요?",
            model=self.model,
            tool_calls=tool_calls_log,
            usage=usage,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
