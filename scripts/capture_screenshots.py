"""README용 스크린샷 자동 캡처.

사전 조건: 백엔드가 http://127.0.0.1:8000 에서 실행 중이고 OPENAI_API_KEY가 설정되어 있어야 한다.

    python scripts/capture_screenshots.py [base_url]

산출물: docs/screenshots/*.png
"""

from __future__ import annotations

import pathlib
import sys

from playwright.sync_api import sync_playwright

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs" / "screenshots"
OUT_DIR.mkdir(parents=True, exist_ok=True)

VIEWPORT = {"width": 1440, "height": 1000}


def send_message(page, text: str) -> None:
    page.fill("#chat-input", text)
    page.click("#send-btn")
    page.wait_for_selector(".typing", timeout=15_000)
    page.wait_for_selector(".typing", state="detached", timeout=180_000)
    page.wait_for_timeout(600)


def main() -> int:
    console_errors: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(
            viewport=VIEWPORT,
            device_scale_factor=2,
            locale="ko-KR",
            timezone_id="Asia/Seoul",
        )
        page = context.new_page()
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda exc: console_errors.append(f"pageerror: {exc}"))

        page.goto(BASE_URL, wait_until="networkidle")
        page.wait_for_function(
            "() => { const el = document.querySelector('#sum-count'); return el && el.textContent.includes('건'); }",
            timeout=60_000,
        )
        page.wait_for_timeout(800)

        # 1) 채팅: 데이터 요약 + 질문/답변
        send_message(page, "이번 달 매출 어때? 가장 좋았던 날도 같이 알려줘.")
        page.wait_for_timeout(500)
        page.screenshot(path=str(OUT_DIR / "01-chat.png"))
        print("saved 01-chat.png")

        # 2) 대화 기록 두 번째 생성
        page.click("#new-chat")
        send_message(page, "주말과 주중 매출은 얼마나 차이 나? 요일별로도 알려줘.")
        page.wait_for_timeout(400)

        # 3) 데이터 관리: 추가 → 수정(CRUD 동작 노출)
        page.click('.tab[data-tab="data"]')
        page.wait_for_timeout(300)
        page.fill("#data-date", "2026-11-07")
        page.fill("#data-value", "745000")
        page.fill("#data-memo", "야간권 프로모션 반영")
        page.click("#data-submit")
        page.wait_for_selector(".toast.is-visible", timeout=30_000)
        page.wait_for_timeout(1200)

        first_row = page.locator("#data-body tr").first
        first_row.locator("[data-edit]").click()
        page.wait_for_timeout(250)
        page.locator('#data-body tr [data-field="value"]').first.fill("752000")
        page.locator('#data-body tr [data-field="memo"]').first.fill("야간권 프로모션 반영 (수정)")
        page.locator("#data-body tr [data-save]").first.click()
        page.wait_for_timeout(900)
        page.screenshot(path=str(OUT_DIR / "02-data-crud.png"))
        print("saved 02-data-crud.png")

        # 4) 대화 기록 불러오기
        page.locator(".conv-item", has_text="이번 달 매출").first.click()
        page.wait_for_timeout(1200)
        page.screenshot(path=str(OUT_DIR / "03-conversations.png"))
        print("saved 03-conversations.png")

        # 5) 인사이트(보너스)
        page.wait_for_timeout(3400)  # 토스트가 사라진 뒤 캡처
        page.click('.tab[data-tab="insight"]')
        page.wait_for_timeout(900)
        page.screenshot(path=str(OUT_DIR / "04-insight.png"))
        print("saved 04-insight.png")

        # 6) 다크 모드(보너스)
        page.click("#theme-toggle")
        page.click('.tab[data-tab="chat"]')
        page.wait_for_timeout(900)
        page.screenshot(path=str(OUT_DIR / "05-dark-mode.png"))
        print("saved 05-dark-mode.png")
        page.click("#theme-toggle")

        context.close()
        browser.close()

    if console_errors:
        print("콘솔 오류:")
        for error in console_errors[:10]:
            print(" -", error)
        return 1
    print("콘솔 오류 없음")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
