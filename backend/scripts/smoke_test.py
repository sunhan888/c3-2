"""실행 중인 서버에 대한 통합 스모크 테스트.

    python scripts/smoke_test.py http://127.0.0.1:8000

데이터 CRUD, 대화 저장/불러오기, 컨텍스트 주입 채팅(도구 호출 포함)을 순서대로 검증한다.
"""

from __future__ import annotations

import json
import sys

import httpx

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
OK = "\033[92mOK\033[0m"
FAIL = "\033[91mFAIL\033[0m"
failures = 0


def check(label: str, condition: bool, detail: object = "") -> None:
    global failures
    if condition:
        print(f"[{OK}] {label}")
    else:
        failures += 1
        print(f"[{FAIL}] {label} -> {detail}")


def main() -> int:
    with httpx.Client(base_url=BASE_URL, timeout=120.0) as client:
        health = client.get("/api/health").json()
        check("헬스 체크", health["status"] == "ok", health)
        check("시드 데이터 365건", health["data_points"] >= 100, health["data_points"])

        summary = client.get("/api/data/summary").json()
        check("요약: 기간/개수/통계/트렌드", all(k in summary for k in ("period", "count", "metrics", "trend")), summary)
        print("     요약:", summary["period"]["label"], summary["count"], "건,", summary["trend"]["label"])

        created = client.post("/api/data", json={"date": "2026-11-07", "value": 712000, "memo": "스모크 테스트"})
        check("데이터 추가(201)", created.status_code == 201, created.text)
        point = created.json()

        duplicated = client.post("/api/data", json={"date": "2026-11-07", "value": 1000, "memo": ""})
        check("중복 날짜 거부(409)", duplicated.status_code == 409, duplicated.status_code)

        updated = client.put(f"/api/data/{point['id']}", json={"memo": "메모 수정됨", "value": 715000})
        check("데이터 수정(200)", updated.status_code == 200 and updated.json()["value"] == 715000, updated.text)

        listed = client.get("/api/data", params={"q": "메모 수정", "limit": 5}).json()
        check("메모 검색", listed["total"] >= 1, listed["total"])

        chat = client.post(
            "/api/chat",
            json={"message": "이번 달(2026년 11월) 매출 흐름과 가장 좋았던 날을 알려줘. 근거 수치도 함께."},
        )
        check("채팅 응답(200)", chat.status_code == 200, chat.text[:400])
        chat_data = chat.json() if chat.status_code == 200 else {}
        if chat_data:
            print("     답변:", chat_data["reply"][:200].replace("\n", " "))
            print("     사용 도구:", [tool["name"] for tool in chat_data["used_tools"]])
            check("컨텍스트 주입 문구", bool(chat_data["context_note"]), chat_data.get("context_note"))
            check("대화 자동 저장", bool(chat_data["conversation_id"]), chat_data.get("conversation_id"))

        conversation_id = chat_data.get("conversation_id")
        follow_up = client.post(
            "/api/chat",
            json={"message": "그럼 지난달과 비교하면 어때?", "conversation_id": conversation_id},
        )
        check("후속 질문(같은 대화)", follow_up.status_code == 200, follow_up.text[:300])
        if follow_up.status_code == 200:
            check(
                "메시지 누적(4개)",
                len(follow_up.json()["messages"]) == 4,
                len(follow_up.json()["messages"]),
            )

        conversations = client.get("/api/conversations").json()
        check("대화 목록 조회", conversations["total"] >= 1, conversations["total"])
        check("목록에는 messages 미포함", "messages" not in conversations["items"][0], conversations["items"][0].keys())

        detail = client.get(f"/api/conversations/{conversation_id}").json()
        check("특정 대화 불러오기(messages 포함)", len(detail["messages"]) == 4, len(detail["messages"]))

        renamed = client.patch(f"/api/conversations/{conversation_id}", json={"title": "11월 매출 점검"})
        check("대화 제목 수정", renamed.status_code == 200 and renamed.json()["title"] == "11월 매출 점검", renamed.text)

        deleted = client.delete(f"/api/data/{point['id']}")
        check("데이터 삭제(200)", deleted.status_code == 200, deleted.text)
        check("삭제 후 조회 404", client.delete(f"/api/data/{point['id']}").status_code == 404)

        export = client.get("/api/data/export", params={"format": "csv"})
        check("CSV 내보내기", export.status_code == 200 and "date,value,memo" in export.text, export.status_code)

    print()
    if failures:
        print(f"{failures}개 검사 실패")
        return 1
    print("모든 검사 통과")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
