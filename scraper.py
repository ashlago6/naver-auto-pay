# ======================================================
# scraper.py - 게시판 크롤링 모듈
# ======================================================

import asyncio
import random
from datetime import date, datetime, timedelta
from playwright.async_api import Page
from config import KEYWORDS, DELAY


def contains_keyword(text: str) -> bool:
    text_lower = text.lower()
    return any(keyword.lower() in text_lower for keyword in KEYWORDS)


async def random_delay(min_sec: float, max_sec: float):
    await asyncio.sleep(random.uniform(min_sec, max_sec))


def parse_post_date(raw: str) -> date | None:
    """
    뽐뿌 날짜 문자열을 date 객체로 변환합니다.
    지원 형식:
      - "HH:MM"        → 오늘
      - "YYYY.MM.DD"   → 해당 날짜  ← 검색결과 페이지 실제 형식
      - "YY/MM/DD"     → 해당 날짜
      - "YYYY-MM-DD"   → 해당 날짜
      - "MM-DD"        → 올해
    """
    raw = raw.strip()
    today = date.today()

    if not raw:
        return None

    # "HH:MM" → 오늘
    if len(raw) == 5 and raw[2] == ":":
        return today

    # "YYYY.MM.DD" ← 뽐뿌 검색결과 실제 형식
    try:
        return datetime.strptime(raw, "%Y.%m.%d").date()
    except ValueError:
        pass

    # "YY/MM/DD"
    try:
        return datetime.strptime(raw, "%y/%m/%d").date()
    except ValueError:
        pass

    # "YYYY-MM-DD"
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        pass

    # "MM-DD" → 올해
    try:
        d = datetime.strptime(raw, "%m-%d").date()
        return d.replace(year=today.year)
    except ValueError:
        pass

    return None


def in_date_range(post_date: date | None, date_from: date, date_to: date) -> bool:
    """post_date 가 [date_from, date_to] 범위 안에 있는지 확인"""
    if post_date is None:
        return True   # 날짜 파싱 실패 시 일단 포함
    return date_from <= post_date <= date_to


async def scrape_ppomppu_board(
    page: Page,
    board_url: str,
    max_pages: int,
    date_from: date,
    date_to: date,
) -> list[dict]:
    """
    뽐뿌 게시판에서 네이버페이 키워드 + 날짜 범위에 맞는 게시글을 추출합니다.
    날짜 범위 내 모든 게시글을 찾을 때까지 자동으로 페이지를 넘깁니다.
    max_pages 는 무한 루프 방지용 안전 상한선입니다.
    """
    found_posts = []

    # 뽐뿌 검색 페이지는 page_no=, 일반 게시판은 page= 사용
    page_param = "page_no" if "search_bbs.php" in board_url else "page"

    for page_num in range(1, max_pages + 1):
        current_url = f"{board_url}&{page_param}={page_num}" if "?" in board_url else f"{board_url}?{page_param}={page_num}"
        print(f"   [PAGE] {page_num}페이지 스캔 중...")

        try:
            # commit: 응답 헤더 수신 즉시 반환 → 이후 리다이렉트가 일어나도 중단 없음
            # wait_for_load_state("load"): 리다이렉트 포함 최종 페이지가 완전히 로드될 때까지 대기
            await page.goto(current_url, wait_until="commit", timeout=30000)
            await page.wait_for_load_state("load", timeout=30000)
            await random_delay(DELAY["page_min"], DELAY["page_max"])

            # 뽐뿌 검색결과 실제 구조:
            # div.conts > div.content > span.title > a  (제목/링크)
            # div.conts > div.content > p.desc > span:3번째 (날짜: YYYY.MM.DD)
            posts = await page.evaluate("""
                () => {
                    const results = [];
                    const BASE = 'https://www.ppomppu.co.kr';

                    document.querySelectorAll('div.conts div.content').forEach(block => {
                        // 제목 링크: span.title > a (첫 번째)
                        const a = block.querySelector('span.title a');
                        if (!a) return;

                        const title = a.textContent.replace(/<[^>]+>/g, '').trim();
                        let href = a.getAttribute('href') || '';
                        if (!href || href.startsWith('javascript')) return;
                        // 상대경로 → 절대경로
                        if (href.startsWith('/')) href = BASE + href;

                        // 날짜: p.desc 안의 span 중 YYYY.MM.DD 패턴
                        let dateStr = '';
                        const desc = block.querySelector('p.desc');
                        if (desc) {
                            desc.querySelectorAll('span').forEach(sp => {
                                const t = sp.textContent.trim();
                                if (/^[0-9]{4}[.][0-9]{2}[.][0-9]{2}$/.test(t)) {
                                    dateStr = t;
                                }
                            });
                        }

                        results.push({ title, url: href, date: dateStr });
                    });

                    return results;
                }
            """)

            if not posts:
                print("   [WARN]  게시글을 하나도 읽지 못했습니다 (선택자 불일치 가능성)")
                break  # 더 이상 페이지가 없는 것으로 판단

            oldest_on_page = None

            for post in posts:
                title     = post.get("title", "")
                date_raw  = post.get("date", "")
                post_date = parse_post_date(date_raw)
                in_range  = in_date_range(post_date, date_from, date_to)
                matched   = contains_keyword(title)

                date_label = post_date.strftime("%Y-%m-%d") if post_date else "날짜미상"
                if matched and in_range:
                    marker = "[OK] 매칭"
                elif matched and not in_range:
                    marker = "[DATE] 범위외"
                else:
                    marker = "   -"
                print(f"   {marker} [{date_label}] {title[:55]}")

                if matched and in_range:
                    if not any(p["url"] == post["url"] for p in found_posts):
                        found_posts.append(post)

                # 페이지 내 가장 오래된 날짜 추적
                if post_date and (oldest_on_page is None or post_date < oldest_on_page):
                    oldest_on_page = post_date

            # 최신순 정렬 기준: 이 페이지의 가장 오래된 글이 시작일보다 이전이면 중단
            if oldest_on_page and oldest_on_page < date_from:
                print(f"   [STOP] 최오래된 글({oldest_on_page}) < 시작일({date_from}) → 다음 페이지 불필요")
                break

            print(f"   >> 다음 페이지로 이동합니다...")

        except Exception:
            print(f"   [WARN]  {page_num}페이지 스캔 중 오류가 발생했습니다.")
            continue

    return found_posts


async def scrape_generic_board(
    page: Page,
    board_url: str,
    max_pages: int,
    date_from: date,
    date_to: date,
) -> list[dict]:
    """일반 게시판 크롤링 (날짜 필터 적용)"""
    found_posts = []

    for page_num in range(1, max_pages + 1):
        current_url = f"{board_url}&page={page_num}" if "?" in board_url else f"{board_url}?page={page_num}"
        print(f"   [PAGE] {page_num}페이지 스캔 중...")

        try:
            await page.goto(current_url, wait_until="load", timeout=30000)
            await random_delay(DELAY["page_min"], DELAY["page_max"])

            posts = await page.evaluate("""
                () => {
                    const results = [];
                    document.querySelectorAll('a').forEach(a => {
                        const title = a.textContent.trim();
                        const href  = a.href || '';
                        if (
                            title.length > 5 && href &&
                            !href.includes('javascript') && !href.includes('#') &&
                            (href.includes('view') || href.includes('read') ||
                             href.includes('no=') || href.includes('idx='))
                        ) {
                            results.push({ title, url: href, date: '' });
                        }
                    });
                    return results;
                }
            """)

            if not posts:
                print("   [WARN]  게시글을 하나도 읽지 못했습니다 (선택자 불일치 가능성)")

            for post in posts:
                title    = post.get("title", "")
                matched  = contains_keyword(title)
                in_range = in_date_range(parse_post_date(post.get("date", "")), date_from, date_to)

                marker = "[OK] 매칭" if (matched and in_range) else "   -"
                print(f"   {marker} {title[:60]}")

                if matched and in_range and not any(p["url"] == post["url"] for p in found_posts):
                    found_posts.append(post)

        except Exception:
            print(f"   [WARN]  {page_num}페이지 스캔 중 오류가 발생했습니다.")
            continue

    return found_posts
