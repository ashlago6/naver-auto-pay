# ======================================================
# main.py - 메인 실행 파일
# ======================================================

import asyncio
import json
import os
import random
import stat
import sys
import tempfile
from datetime import date, datetime, timedelta
from urllib.parse import urlparse
from playwright.async_api import async_playwright
from config import BOARDS, SESSION_FILE, VISITED_FILE, DELAY, ALLOWED_DOMAINS
from scraper import scrape_ppomppu_board, scrape_generic_board
from clicker import find_and_click_naverpay_links

# Windows 터미널 UTF-8 출력 강제
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# ── 보안: URL 검증 ────────────────────────────────────────
def is_safe_url(url: str) -> bool:
    """http/https 스킴이고 허용된 도메인인지 확인합니다."""
    try:
        p = urlparse(url)
        if p.scheme not in ("http", "https"):
            return False
        if not p.netloc:
            return False
        return any(p.netloc == d or p.netloc.endswith("." + d) for d in ALLOWED_DOMAINS)
    except Exception:
        return False


# ── 보안: visited.json 원자적 쓰기 ───────────────────────
def load_visited() -> set:
    if os.path.exists(VISITED_FILE):
        try:
            with open(VISITED_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except (json.JSONDecodeError, OSError):
            print("[WARN] visited.json 손상. 빈 목록으로 시작합니다.")
    return set()


def save_visited(visited: set):
    """임시 파일에 먼저 쓰고 원자적으로 교체해 데이터 손상을 방지합니다."""
    visited_dir = os.path.dirname(VISITED_FILE) or "."
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", dir=visited_dir,
            delete=False, encoding="utf-8", suffix=".tmp"
        ) as tmp:
            json.dump(list(visited), tmp, ensure_ascii=False, indent=2)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp_path = tmp.name
        os.replace(tmp_path, VISITED_FILE)
        # 소유자만 읽기/쓰기
        try:
            os.chmod(VISITED_FILE, stat.S_IRUSR | stat.S_IWUSR)
        except Exception:
            pass
    except Exception:
        print("[WARN] visited.json 저장 중 오류가 발생했습니다.")


# ── 날짜 범위 선택 ────────────────────────────────────────
def select_date_range() -> tuple[date, date]:
    today = date.today()
    max_past_days = 90  # 90일 이전 날짜는 거절

    print()
    print("=" * 50)
    print("  날짜 범위 선택")
    print("=" * 50)
    print(f"  오늘: {today.strftime('%Y-%m-%d')}")
    print()
    print("  1. 오늘만")
    print("  2. 오늘 ~ 1일 전")
    print("  3. 오늘 ~ 3일 전")
    print("  4. 오늘 ~ 1주일 전")
    print("  5. 직접 입력")
    print()

    while True:
        choice = input("  선택 (1~5): ").strip()

        if choice == "1":
            return today, today
        elif choice == "2":
            return today - timedelta(days=1), today
        elif choice == "3":
            return today - timedelta(days=3), today
        elif choice == "4":
            return today - timedelta(days=7), today
        elif choice == "5":
            print()
            print("  * 직접 입력 시 날짜 범위는 최대 7일로 제한됩니다.")
            print("  * 미래 날짜 및 90일 이전 날짜는 입력할 수 없습니다.")
            print("  * 종료일을 비워두면 오늘 날짜로 자동 설정됩니다.")
            print()

            # 시작일 입력
            while True:
                s = input("  시작일 (YYYY-MM-DD): ").strip()
                try:
                    date_from = datetime.strptime(s, "%Y-%m-%d").date()
                    if date_from > today:
                        print("  미래 날짜는 입력할 수 없습니다.")
                        continue
                    if (today - date_from).days > max_past_days:
                        print(f"  {max_past_days}일 이전 날짜는 입력할 수 없습니다.")
                        continue
                    break
                except ValueError:
                    print("  형식이 올바르지 않습니다. 예: 2025-03-10")

            # 종료일 입력
            while True:
                s = input(f"  종료일 (YYYY-MM-DD, 비워두면 오늘 {today}): ").strip()
                try:
                    date_to = datetime.strptime(s, "%Y-%m-%d").date() if s else today
                    if date_to > today:
                        print("  미래 날짜는 입력할 수 없습니다.")
                        continue
                    break
                except ValueError:
                    print("  형식이 올바르지 않습니다. 예: 2025-03-15")

            if date_from > date_to:
                date_from, date_to = date_to, date_from

            if (date_to - date_from).days > 7:
                print("  [WARN] 범위가 7일을 초과해 종료일 기준 7일 전으로 시작일을 조정합니다.")
                date_from = date_to - timedelta(days=7)

            print()
            print(f"  [DATE] 탐색 범위: {date_from.strftime('%Y-%m-%d')} ~ {date_to.strftime('%Y-%m-%d')}")
            print()
            return date_from, date_to
        else:
            print("  1~5 중에서 선택해 주세요.")


def print_banner():
    print()
    print("=" * 55)
    print("   NaverPay Auto Clicker")
    print(f"   Start: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 55)


async def scan_once(page, context, visited: set, date_from, date_to) -> tuple[int, int]:
    """지정된 날짜 범위로 게시판을 한 번 스캔합니다."""
    total_found   = 0
    total_clicked = 0

    for board in BOARDS:
        board_name = board["name"]
        board_url  = board["url"]
        max_pages  = board.get("pages", 2)

        # 게시판 URL 안전성 검사
        if not is_safe_url(board_url):
            print(f"[WARN] 허용되지 않은 게시판 URL 건너뜀: {board_url[:60]}")
            continue

        print(f"[SCAN] 게시판: {board_name}")
        print()

        if "ppomppu" in board_url:
            posts = await scrape_ppomppu_board(page, board_url, max_pages, date_from, date_to)
        else:
            posts = await scrape_generic_board(page, board_url, max_pages, date_from, date_to)

        print()
        print(f"[RESULT] 키워드+날짜 매칭 게시글: {len(posts)}개")
        print()

        new_posts  = [p for p in posts if p["url"] not in visited]
        skip_count = len(posts) - len(new_posts)

        if skip_count > 0:
            print(f"[SKIP] 이미 처리한 게시글 {skip_count}개 건너뜀")

        if not new_posts:
            print("[INFO] 새로운 게시글 없음")
            print()
            continue

        print(f"[NEW] 새로운 게시글 {len(new_posts)}개 처리 시작")
        print()

        for idx, post in enumerate(new_posts, 1):
            post_url = post.get("url", "")

            # 게시글 URL 안전성 검사
            if not is_safe_url(post_url):
                print(f"   [SKIP] 허용되지 않은 URL: {post_url[:60]}")
                continue

            print(f"   [{idx}/{len(new_posts)}] {post['title'][:50]}...")

            wait_time = random.uniform(DELAY["post_min"], DELAY["post_max"])
            print(f"   >> {wait_time:.1f}초 대기...")
            await asyncio.sleep(wait_time)

            clicked = await find_and_click_naverpay_links(page, context, post_url, visited)

            visited.add(post_url)
            save_visited(visited)

            total_found   += 1
            total_clicked += clicked
            print()

    return total_found, total_clicked


async def main():
    print_banner()

    if not os.path.exists(SESSION_FILE):
        print("[ERROR] session.json 없음. login.bat 먼저 실행하세요.")
        input("아무 키나 눌러 종료...")
        return

    visited = load_visited()
    print(f"[INFO] 이미 처리한 게시글/링크: {len(visited)}개")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=[
                "--start-maximized",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-extensions",
                "--disable-plugins",
                "--mute-audio",
            ],
        )
        context = await browser.new_context(
            storage_state=SESSION_FILE,
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            ignore_https_errors=False,   # HTTPS 인증서 오류 허용 안 함
            permissions=[],              # 브라우저 권한 전부 거절
        )
        page = await context.new_page()

        while True:
            date_from, date_to = select_date_range()

            found, clicked = await scan_once(page, context, visited, date_from, date_to)

            print("=" * 55)
            print("   이번 탐색 완료!")
            print(f"   처리 게시글: {found}개  /  클릭 링크: {clicked}개")
            print("=" * 55)
            print()

            print("  1. 계속 탐색 (날짜 범위 다시 선택)")
            print("  2. 프로그램 종료")
            print()
            while True:
                ans = input("  선택 (1 or 2): ").strip()
                if ans in ("1", "2"):
                    break
                print("  1 또는 2를 입력하세요.")

            print()
            if ans == "2":
                break

        await browser.close()

    print("[INFO] 프로그램을 종료합니다.")
    print()
    input("아무 키나 눌러 창을 닫으세요...")


if __name__ == "__main__":
    asyncio.run(main())
