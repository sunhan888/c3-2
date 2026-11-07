"""Render 배포 자동화 스크립트.

사용 예:
    RENDER_API_KEY=rnd_xxx python scripts/deploy_render.py \
        --openai-key sk-... \
        --firebase-json firebase-service-account.json

공개 GitHub 저장소(sunhan888/c3-2)의 backend 디렉터리를 Render Web Service로 배포하고,
배포가 끝나면 서비스 URL을 출력한다. 키는 Render 환경변수로만 저장되며 저장소에 기록하지 않는다.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

API = "https://api.render.com/v1"
REPO = "https://github.com/sunhan888/c3-2"
NAME = "datamate-api"


def call(method: str, path: str, key: str, payload: dict | None = None) -> tuple[int, dict | list | str]:
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        f"{API}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = response.read().decode()
            return response.status, (json.loads(body) if body else {})
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--openai-key", default=os.environ.get("OPENAI_API_KEY", ""))
    parser.add_argument("--firebase-json", default="", help="서비스 계정 JSON 파일 경로")
    parser.add_argument("--openai-model", default="gpt-4o-mini")
    args = parser.parse_args()

    key = os.environ.get("RENDER_API_KEY", "")
    if not key:
        print("RENDER_API_KEY 환경변수가 필요합니다.")
        return 1

    status, owners = call("GET", "/owners?limit=1", key)
    if status != 200:
        print(f"소유자 조회 실패 ({status}): {owners}")
        return 1
    owner_id = owners[0]["owner"]["id"]
    print(f"owner: {owner_id}")

    env_vars = [
        {"key": "PYTHON_VERSION", "value": "3.12.3"},
        {"key": "OPENAI_MODEL", "value": args.openai_model},
        {"key": "OPENAI_MAX_TOKENS", "value": "700"},
        {"key": "STORAGE_BACKEND", "value": "auto"},
        {"key": "SEED_ON_STARTUP", "value": "true"},
        {"key": "ALLOWED_ORIGINS", "value": "*"},
        {"key": "DEMO_FALLBACK", "value": "false" if args.openai_key else "true"},
    ]
    if args.openai_key:
        env_vars.append({"key": "OPENAI_API_KEY", "value": args.openai_key})
    if args.firebase_json:
        with open(args.firebase_json, encoding="utf-8") as handle:
            env_vars.append({"key": "FIREBASE_SERVICE_ACCOUNT_JSON", "value": handle.read()})

    payload = {
        "type": "web_service",
        "name": NAME,
        "ownerId": owner_id,
        "repo": REPO,
        "branch": "main",
        "rootDir": "backend",
        "autoDeploy": "no",
        "envVars": env_vars,
        "serviceDetails": {
            "env": "python",
            "plan": "free",
            "region": "singapore",
            "healthCheckPath": "/api/health",
            "envSpecificDetails": {
                "buildCommand": "pip install -r requirements.txt",
                "startCommand": "uvicorn main:app --host 0.0.0.0 --port $PORT",
            },
        },
    }

    status, created = call("POST", "/services", key, payload)
    if status not in (200, 201):
        print(f"서비스 생성 실패 ({status}): {created}")
        return 1

    service = created.get("service", created)
    service_id = service["id"]
    print(f"service: {service_id}")

    for attempt in range(60):
        time.sleep(10)
        status, detail = call("GET", f"/services/{service_id}", key)
        if status != 200:
            print(f"상태 조회 실패 ({status})")
            continue
        info = detail.get("serviceDetails", {})
        url = info.get("url") or "(대기 중)"
        deploys = detail.get("deploys") or []
        state = deploys[0].get("status") if deploys else "pending"
        print(f"[{attempt * 10:>3}s] status={state} url={url}")
        if url and url != "(대기 중)" and state in ("live", "build_succeeded"):
            print(f"\n배포 완료: {url}")
            print(f"Swagger: {url}/docs")
            return 0
        if state in ("build_failed", "canceled", "deactivated"):
            print("배포 실패 — Render 대시보드 로그를 확인하세요.")
            return 1

    print("시간 내에 배포가 끝나지 않았습니다. Render 대시보드에서 확인하세요.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
