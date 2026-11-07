"""데이터 API: CRUD 4종 + summary/statistics/export."""

from __future__ import annotations

import csv
import io
import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.api.deps import settings_dependency, store_dependency
from app.core.config import Settings
from app.models.schemas import (
    DataPointCreate,
    DataPointListOut,
    DataPointOut,
    DataPointUpdate,
    StatisticsOut,
    SummaryOut,
)
from app.repositories.base import Store
from app.services.analytics import build_statistics, build_summary, filter_points

router = APIRouter(prefix="/api/data", tags=["데이터"])


@router.get(
    "/summary",
    response_model=SummaryOut,
    summary="데이터 요약 조회",
    description="기간, 레코드 수, 합계/평균/최대/최소, 최근 트렌드를 반환합니다. 채팅 컨텍스트 주입에 사용됩니다.",
)
def get_summary(
    window_days: int = Query(30, ge=2, le=180, description="트렌드 비교 구간(일)"),
    recent_days: int = Query(7, ge=1, le=30, description="최근 데이터 표시 개수"),
    store: Store = Depends(store_dependency),
    settings: Settings = Depends(settings_dependency),
) -> dict:
    points = store.list_points()
    return build_summary(
        points,
        topic=settings.data_topic,
        unit=settings.data_unit,
        window_days=window_days,
        recent_days=recent_days,
    )


@router.get(
    "/statistics",
    response_model=StatisticsOut,
    summary="확장 통계 조회 (보너스)",
    description="월별/요일별 평균, 변동성, 최근 7일 성장률, 7일 이동평균을 반환합니다.",
)
def get_statistics(
    months: int = Query(12, ge=1, le=36, description="월별 통계로 표시할 최근 개월 수"),
    store: Store = Depends(store_dependency),
    settings: Settings = Depends(settings_dependency),
) -> dict:
    points = store.list_points()
    return build_statistics(
        points, topic=settings.data_topic, unit=settings.data_unit, months=months
    )


@router.get(
    "/export",
    summary="데이터 내보내기 (보너스)",
    description="CSV 또는 JSON 파일로 다운로드합니다.",
    response_class=Response,
)
def export_data(
    format: str = Query("csv", pattern="^(csv|json)$", description="csv 또는 json"),
    store: Store = Depends(store_dependency),
    settings: Settings = Depends(settings_dependency),
) -> Response:
    points = filter_points(store.list_points(), None, None)
    rows = [
        {"date": item["date"].isoformat(), "value": round(item["value"]), "memo": item.get("memo", "")}
        for item in points
    ]
    if format == "json":
        payload = json.dumps(rows, ensure_ascii=False, indent=2)
        return Response(
            content=payload,
            media_type="application/json; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="datamate-data.json"'},
        )

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=["date", "value", "memo"])
    writer.writeheader()
    writer.writerows(rows)
    return Response(
        content="\ufeff" + buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="datamate-data.csv"'},
    )


@router.get(
    "",
    response_model=DataPointListOut,
    summary="데이터 목록 조회",
    description="날짜/메모 필터와 페이지네이션을 지원합니다. 기본은 최신순 정렬입니다.",
)
def list_data(
    start_date: date | None = Query(None, description="조회 시작일"),
    end_date: date | None = Query(None, description="조회 종료일"),
    q: str | None = Query(None, max_length=50, description="메모 검색어"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    store: Store = Depends(store_dependency),
    settings: Settings = Depends(settings_dependency),
) -> dict:
    points = filter_points(store.list_points(), start_date, end_date)
    if q:
        keyword = q.strip().lower()
        points = [item for item in points if keyword in str(item.get("memo", "")).lower()]
    total = len(points)
    ordered = list(reversed(points)) if order == "desc" else points
    window = ordered[offset : offset + limit]
    items = [
        {
            "id": item["id"],
            "date": item["date"],
            "value": round(item["value"]),
            "memo": item.get("memo", ""),
            "created_at": item.get("created_at"),
            "updated_at": item.get("updated_at"),
        }
        for item in window
    ]
    note = ""
    if points:
        note = f"{total}건 · {points[0]['date'].isoformat()} ~ {points[-1]['date'].isoformat()}"
    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "unit": settings.data_unit,
        "summary_note": note,
    }


@router.post(
    "",
    response_model=DataPointOut,
    status_code=status.HTTP_201_CREATED,
    summary="데이터 추가",
    description="(date, value, memo)를 저장합니다. 같은 날짜 데이터가 이미 있으면 409를 반환합니다.",
)
def create_data(
    payload: DataPointCreate,
    store: Store = Depends(store_dependency),
) -> dict:
    day = payload.date.isoformat()
    if store.find_point_by_date(day):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "duplicate_date",
                "message": f"{day} 데이터가 이미 존재합니다. 수정(PUT)을 사용해 주세요.",
            },
        )
    return store.add_point(day, payload.value, payload.memo)


@router.put(
    "/{point_id}",
    response_model=DataPointOut,
    summary="데이터 수정",
    description="날짜/값/메모를 부분 수정합니다.",
)
def update_data(
    point_id: str,
    payload: DataPointUpdate,
    store: Store = Depends(store_dependency),
) -> dict:
    if not payload.has_changes():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "no_changes", "message": "수정할 값이 없습니다."},
        )
    changes: dict = {}
    if payload.date is not None:
        day = payload.date.isoformat()
        existing = store.find_point_by_date(day)
        if existing and existing["id"] != point_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "duplicate_date", "message": f"{day} 데이터가 이미 존재합니다."},
            )
        changes["date"] = day
    if payload.value is not None:
        changes["value"] = payload.value
    if payload.memo is not None:
        changes["memo"] = payload.memo
    updated = store.update_point(point_id, changes)
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "해당 데이터를 찾을 수 없습니다."},
        )
    return updated


@router.delete(
    "/{point_id}",
    summary="데이터 삭제",
    description="데이터를 삭제하고 삭제 여부를 반환합니다.",
)
def delete_data(point_id: str, store: Store = Depends(store_dependency)) -> dict:
    deleted = store.delete_point(point_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "해당 데이터를 찾을 수 없습니다."},
        )
    return {"deleted": True, "id": point_id}
