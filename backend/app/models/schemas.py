"""Pydantic 스키마.

요청 데이터 검증(날짜 형식, 값 범위, 메모 길이)과 Swagger 문서화를 동시에 담당한다.
"""

from __future__ import annotations

from datetime import date as DateType
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Role = Literal["user", "assistant", "system"]


class DataPointCreate(BaseModel):
    date: DateType = Field(description="데이터 기준일 (YYYY-MM-DD)")
    value: float = Field(gt=0, le=1_000_000_000, description="측정값(원). 0보다 커야 한다.")
    memo: str = Field(default="", max_length=200, description="메모(선택)")

    @field_validator("memo")
    @classmethod
    def strip_memo(cls, value: str) -> str:
        return value.strip()


class DataPointUpdate(BaseModel):
    date: DateType | None = Field(default=None, description="변경할 날짜")
    value: float | None = Field(default=None, gt=0, le=1_000_000_000, description="변경할 값")
    memo: str | None = Field(default=None, max_length=200, description="변경할 메모")

    @field_validator("memo")
    @classmethod
    def strip_memo(cls, value: str | None) -> str | None:
        return value.strip() if isinstance(value, str) else value

    def has_changes(self) -> bool:
        return any(getattr(self, name) is not None for name in ("date", "value", "memo"))


class DataPointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    date: DateType
    value: float
    memo: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DataPointListOut(BaseModel):
    items: list[DataPointOut]
    total: int = Field(description="필터 조건에 해당하는 전체 레코드 수")
    limit: int
    offset: int
    unit: str
    summary_note: str = Field(default="", description="목록 상단에 표시할 요약 안내 문구")


class Period(BaseModel):
    start: DateType
    end: DateType
    label: str
    days: int


class Metrics(BaseModel):
    total: float = Field(description="기간 합계")
    average: float = Field(description="일평균")
    max: float
    min: float
    median: float
    latest: float = Field(description="가장 최근 레코드 값")


class Trend(BaseModel):
    direction: Literal["상승", "하락", "유지"]
    change_pct: float = Field(description="직전 동일 구간 대비 변화율(%)")
    window_days: int
    label: str
    recent_average: float
    previous_average: float


class Extreme(BaseModel):
    date: DateType
    value: float
    memo: str = ""


class Extremes(BaseModel):
    best: Extreme
    worst: Extreme


class RecentPoint(BaseModel):
    date: DateType
    value: float


class SummaryOut(BaseModel):
    topic: str
    unit: str
    period: Period | None = None
    count: int
    metrics: Metrics | None = None
    trend: Trend | None = None
    extremes: Extremes | None = None
    recent: list[RecentPoint] = Field(default_factory=list)
    generated_at: datetime
    empty: bool = False


class MonthlyStat(BaseModel):
    month: str
    count: int
    total: float
    average: float
    change_pct: float | None = None


class WeekdayStat(BaseModel):
    weekday: str
    count: int
    average: float
    index: float = Field(description="전체 평균 대비 지수(1.0 = 평균)")


class Volatility(BaseModel):
    std_dev: float
    coefficient_of_variation: float


class GrowthBlock(BaseModel):
    last_7_avg: float
    prev_7_avg: float
    change_pct: float


class MovingAveragePoint(BaseModel):
    date: DateType
    value: float
    ma7: float


class StatisticsOut(BaseModel):
    topic: str
    unit: str
    count: int
    monthly: list[MonthlyStat]
    weekday: list[WeekdayStat]
    weekend_vs_weekday: dict[str, float]
    volatility: Volatility
    growth: GrowthBlock
    moving_average: list[MovingAveragePoint]
    top_months: list[MonthlyStat]
    generated_at: datetime


class Message(BaseModel):
    role: Role
    content: str = Field(min_length=1, max_length=8000)
    created_at: datetime | None = None


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=80, description="미지정 시 자동 생성")
    messages: list[Message] = Field(default_factory=list, max_length=200)


class ConversationUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=80)


class ConversationSummary(BaseModel):
    id: str
    title: str
    message_count: int
    preview: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
    model: str | None = None


class ConversationDetail(ConversationSummary):
    messages: list[Message] = Field(default_factory=list)


class ConversationListOut(BaseModel):
    items: list[ConversationSummary]
    total: int
    limit: int
    offset: int
    includes_messages: bool = Field(
        default=False,
        description="false면 목록에는 messages가 포함되지 않는다. 전체 메시지는 GET /api/conversations/{id}로 조회.",
    )


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000, description="사용자 질문")
    conversation_id: str | None = Field(default=None, description="이어서 대화할 기존 대화 ID")
    save: bool = Field(default=True, description="false면 대화를 저장하지 않는다.")

    @field_validator("message")
    @classmethod
    def strip_message(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("메시지가 비어 있습니다.")
        return stripped


class ToolCallLog(BaseModel):
    name: str
    arguments: dict
    ok: bool
    summary: str


class ChatResponse(BaseModel):
    conversation_id: str
    reply: str
    messages: list[Message]
    model: str
    used_tools: list[ToolCallLog] = Field(default_factory=list)
    latency_ms: int
    saved: bool
    summary: SummaryOut
    context_note: str = Field(description="이번 답변에 주입된 데이터 요약 한 줄 요약")


class HealthOut(BaseModel):
    status: str
    app: str
    version: str
    storage_backend: str
    model: str
    tools_enabled: bool
    data_points: int
    conversations: int
    llm_configured: bool
    time: datetime
