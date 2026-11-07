"""핵심 요구사항 자동 검증."""

from __future__ import annotations

from app.services.ai_service import AIResult


def test_health_and_seed(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["storage_backend"] == "local"
    assert body["data_points"] >= 100


def test_summary_contract(client):
    body = client.get("/api/data/summary").json()
    assert set(body) >= {"period", "count", "metrics", "trend", "extremes", "recent"}
    assert body["count"] >= 100
    assert body["metrics"]["max"] >= body["metrics"]["min"]
    assert body["trend"]["direction"] in {"상승", "하락", "유지"}


def test_statistics_contract(client):
    body = client.get("/api/data/statistics").json()
    assert len(body["weekday"]) == 7
    assert body["monthly"]
    assert body["moving_average"]
    assert "coefficient_of_variation" in body["volatility"]


def test_data_crud(client):
    payload = {"date": "2030-01-01", "value": 500000, "memo": "테스트 추가"}
    created = client.post("/api/data", json=payload)
    assert created.status_code == 201
    point = created.json()
    assert point["value"] == 500000

    duplicate = client.post("/api/data", json=payload)
    assert duplicate.status_code == 409

    updated = client.put(f"/api/data/{point['id']}", json={"value": 515000, "memo": "수정됨"})
    assert updated.status_code == 200
    assert updated.json()["value"] == 515000

    listed = client.get("/api/data", params={"q": "수정됨"}).json()
    assert listed["total"] == 1
    assert listed["items"][0]["memo"] == "수정됨"

    assert client.delete(f"/api/data/{point['id']}").status_code == 200
    assert client.delete(f"/api/data/{point['id']}").status_code == 404


def test_validation_rejects_bad_value(client):
    invalid = client.post("/api/data", json={"date": "2030-02-01", "value": -1, "memo": ""})
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "validation_error"

    bad_date = client.post("/api/data", json={"date": "2026-13-40", "value": 1000})
    assert bad_date.status_code == 422


def test_export_csv(client):
    response = client.get("/api/data/export", params={"format": "csv"})
    assert response.status_code == 200
    assert "date,value,memo" in response.text
    assert "attachment" in response.headers["content-disposition"]


def test_chat_injects_context_and_saves(client, monkeypatch):
    captured = {}

    def fake_complete(self, messages, tool_executor=None, tools=None):
        captured["system"] = messages[0]["content"]
        captured["messages"] = messages
        return AIResult(content="컨텍스트 기반 테스트 답변", model="test-model")

    monkeypatch.setattr("app.services.ai_service.AIService.complete", fake_complete)

    response = client.post("/api/chat", json={"message": "이번 달 매출 어때?"})
    assert response.status_code == 200
    body = response.json()

    assert "사용자 데이터 요약" in captured["system"]
    assert "최근 트렌드" in captured["system"]
    assert body["reply"] == "컨텍스트 기반 테스트 답변"
    assert body["conversation_id"]
    assert body["context_note"]
    assert len(body["messages"]) == 2

    detail = client.get(f"/api/conversations/{body['conversation_id']}").json()
    assert detail["messages"][0]["content"] == "이번 달 매출 어때?"

    follow_up = client.post(
        "/api/chat",
        json={"message": "그럼 지난달은?", "conversation_id": body["conversation_id"]},
    )
    assert follow_up.status_code == 200
    assert len(follow_up.json()["messages"]) == 4


def test_chat_demo_fallback_without_key(client):
    response = client.post("/api/chat", json={"message": "가장 매출이 좋았던 날은?"})
    assert response.status_code == 200
    assert "데모 모드" in response.json()["reply"]


def test_conversation_crud(client):
    created = client.post(
        "/api/conversations",
        json={"title": "테스트 대화", "messages": [{"role": "user", "content": "안녕"}]},
    )
    assert created.status_code == 201
    conversation = created.json()
    assert conversation["messages"][0]["content"] == "안녕"

    listed = client.get("/api/conversations").json()
    assert listed["total"] >= 1
    assert "messages" not in listed["items"][0]

    fetched = client.get(f"/api/conversations/{conversation['id']}").json()
    assert len(fetched["messages"]) == 1

    renamed = client.patch(f"/api/conversations/{conversation['id']}", json={"title": "새 제목"})
    assert renamed.json()["title"] == "새 제목"

    assert client.delete(f"/api/conversations/{conversation['id']}").status_code == 200
    assert client.get(f"/api/conversations/{conversation['id']}").status_code == 404


def test_openapi_documents_endpoints(client):
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]
    for path in ["/api/data", "/api/data/{point_id}", "/api/data/summary", "/api/chat", "/api/conversations"]:
        assert path in paths
