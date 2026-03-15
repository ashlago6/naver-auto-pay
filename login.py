# ======================================================
# login.py - 최초 1회 수동 로그인 & 세션 저장
# 이 파일은 처음 한 번만 실행하면 됩니다.
# 브라우저에서 직접 로그인한 뒤 Enter를 눌러 세션을 저장합니다.
# ======================================================

import asyncio
import os
import stat
import sys
from playwright.async_api import async_playwright
from config import SESSION_FILE

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def restrict_file_permissions(path: str):
    """파일을 소유자만 읽고 쓸 수 있도록 권한을 제한합니다 (Windows 호환)."""
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except Exception:
        pass  # Windows 일부 환경에서는 chmod가 제한적으로 동작


async def wait_for_enter(message: str):
    """이벤트 루프를 차단하지 않고 Enter 입력을 기다립니다."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, input, message)


async def manual_login():
    print("=" * 50)
    print("  네이버 로그인 세션 저장 프로그램")
    print("=" * 50)
    print()

    if os.path.exists(SESSION_FILE):
        print(f"이미 저장된 세션 파일({SESSION_FILE})이 있습니다.")
        answer = input("   다시 로그인하여 덮어쓰겠습니까? (y/n): ").strip().lower()
        if answer != "y":
            print("   취소되었습니다. 기존 세션을 유지합니다.")
            input("\n아무 키나 눌러 창을 닫으세요...")
            return

    print()
    print("브라우저가 열립니다. 네이버에 로그인해 주세요.")
    print("로그인 완료 후 이 창(터미널)으로 돌아와 Enter를 눌러주세요.")
    print()

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=False,
                args=["--start-maximized"],
            )
            context = await browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            )
            page = await context.new_page()

            # 네이버 로그인 페이지 열기
            await page.goto("https://nid.naver.com/nidlogin.login", wait_until="domcontentloaded")

            # ★ 핵심 수정: 이벤트 루프를 막지 않는 방식으로 Enter 대기
            await wait_for_enter("로그인 완료 후 Enter를 누르세요... ")

            print()
            print("세션 저장 중...")

            # 세션(쿠키 포함) 즉시 저장 — 재탐색 없이 바로 저장
            await context.storage_state(path=SESSION_FILE)

            await browser.close()

        # 저장 확인 + 파일 권한 제한 (소유자만 읽기/쓰기)
        if os.path.exists(SESSION_FILE) and os.path.getsize(SESSION_FILE) > 0:
            restrict_file_permissions(SESSION_FILE)
            print(f"세션이 저장되었습니다!")
            print("이제 run.bat을 실행하면 자동으로 로그인된 상태로 동작합니다.")
        else:
            print("오류: 세션 파일이 생성되지 않았습니다. 다시 시도해 주세요.")

    except Exception:
        # 민감한 스택 정보 노출 방지
        print("\n오류가 발생했습니다. 다시 시도해 주세요.")

    print()
    input("아무 키나 눌러 창을 닫으세요...")


if __name__ == "__main__":
    asyncio.run(manual_login())
