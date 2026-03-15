# ======================================================
# clicker.py - 네이버페이 링크 자동 클릭 모듈
# ======================================================

import asyncio
import random
import re
from urllib.parse import urlparse
from playwright.async_api import Page, BrowserContext
from config import DELAY, NAVERPAY_LINK_PATTERNS, ALLOWED_DOMAINS

# config.py의 단일 패턴 목록 사용 (중복 정의 제거)
NAVERPAY_PATTERNS = NAVERPAY_LINK_PATTERNS

# 본문 텍스트에서 URL을 추출하는 정규표현식
URL_REGEX = re.compile(r'https?://[^\s\'"<>）)]+')


async def random_delay(min_sec: float, max_sec: float):
    wait_time = random.uniform(min_sec, max_sec)
    await asyncio.sleep(wait_time)


async def human_like_scroll(page: Page):
    for _ in range(random.randint(3, 6)):
        await page.mouse.wheel(0, random.randint(200, 500))
        await asyncio.sleep(random.uniform(0.3, 0.8))


def is_safe_url(url: str) -> bool:
    """http/https 스킴이고 허용된 도메인인지 검증합니다."""
    try:
        p = urlparse(url)
        if p.scheme not in ("http", "https"):
            return False
        if not p.netloc:
            return False
        return any(p.netloc == d or p.netloc.endswith("." + d) for d in ALLOWED_DOMAINS)
    except Exception:
        return False


def is_naverpay_url(url: str) -> bool:
    if not is_safe_url(url):
        return False
    url_lower = url.lower()
    return any(p in url_lower for p in NAVERPAY_PATTERNS)


def deduplicate(urls: list[str]) -> list[str]:
    seen = set()
    result = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            result.append(u)
    return result


async def collect_links_from_post(page: Page) -> list[str]:
    """
    게시글 본문에서 네이버페이 적립 링크를 모두 수집합니다.
    1) 본문 <a href> 태그
    2) 본문 텍스트에 적힌 URL (정규표현식)
    3) 첨부 링크 영역 (링크1, 링크2 버튼 등)
    """
    collected = []

    # ── 1) 본문 <a> 태그 href 수집 ─────────────────────────
    href_links: list[str] = await page.evaluate("""
        () => {
            const bodySelectors = [
                'div.board-contents',
                'td.board-contents',
                'div.post-content',
                'div.view-content',
                'div#content',
                'td#content',
            ];

            let container = null;
            for (const sel of bodySelectors) {
                container = document.querySelector(sel);
                if (container) break;
            }

            // 본문 컨테이너를 못 찾으면 body 전체에서 시도
            if (!container) container = document.body;

            const links = [];
            container.querySelectorAll('a[href]').forEach(a => {
                const href = a.href || '';
                if (href && !href.startsWith('javascript')) {
                    links.push(href);
                }
            });
            return links;
        }
    """)
    collected.extend(href_links)

    # ── 2) 본문 텍스트에서 URL 정규표현식 추출 ──────────────
    body_text: str = await page.evaluate("""
        () => {
            const bodySelectors = [
                'div.board-contents',
                'td.board-contents',
                'div.post-content',
                'div.view-content',
            ];
            for (const sel of bodySelectors) {
                const el = document.querySelector(sel);
                if (el) return el.innerText || el.textContent || '';
            }
            return document.body.innerText || '';
        }
    """)
    text_urls = URL_REGEX.findall(body_text)
    collected.extend(text_urls)

    # ── 3) 첨부 링크 영역 (링크1, 링크2 버튼 등) ─────────────
    attach_links: list[str] = await page.evaluate("""
        () => {
            const links = [];
            // 뽐뿌 스타일 첨부 링크
            const attachSelectors = [
                'a[href*="link"]',
                'div.attach a',
                'td.attach a',
                '.file_list a',
                '.link_list a',
            ];
            attachSelectors.forEach(sel => {
                document.querySelectorAll(sel).forEach(a => {
                    const href = a.href || '';
                    if (href && !href.startsWith('javascript')) {
                        links.push(href);
                    }
                });
            });

            // '링크1', '링크2' 텍스트를 가진 모든 <a> 태그
            document.querySelectorAll('a').forEach(a => {
                const text = a.textContent.trim();
                if (/^링크 *[0-9]*$|^link *[0-9]*$/i.test(text)) {
                    const href = a.href || '';
                    if (href && !href.startsWith('javascript')) {
                        links.push(href);
                    }
                }
            });

            return links;
        }
    """)
    collected.extend(attach_links)

    # 중복 제거 후 네이버페이 패턴 필터링
    all_urls = deduplicate(collected)
    naverpay_urls = [u for u in all_urls if is_naverpay_url(u)]

    return naverpay_urls


async def find_and_click_naverpay_links(
    page: Page,
    context: BrowserContext,
    post_url: str,
    visited: set,
) -> int:
    """
    게시글을 열고 네이버페이 적립 링크를 찾아 클릭합니다.
    visited: 이미 접속한 링크 URL 집합 (중복 방지, 클릭 후 자동 추가)
    반환값: 클릭한 링크 수
    """
    clicked_count = 0

    try:
        print(f"   [FIND] 게시글 열기: {post_url[:70]}...")
        await page.goto(post_url, wait_until="domcontentloaded", timeout=30000)
        await random_delay(DELAY["page_min"], DELAY["page_max"])
        await human_like_scroll(page)
        await random_delay(DELAY["action_min"], DELAY["action_max"])

        naverpay_urls = await collect_links_from_post(page)

        if not naverpay_urls:
            print("   [INFO]  본문에서 적립 패턴을 찾지 못함")
            return 0

        print(f"   [LINK] 총 {len(naverpay_urls)}개 링크 발견:")
        for url in naverpay_urls:
            already = "(이미 접속함 - 건너뜀)" if url in visited else ""
            print(f"      링크 발견: {url} {already}")

        # 발견된 링크 하나씩 클릭 (이미 접속한 링크 또는 안전하지 않은 URL 건너뜀)
        for url in naverpay_urls:
            if url in visited:
                print(f"   [SKIP] 이미 접속한 링크: {url[:70]}")
                continue

            if not is_safe_url(url):
                print(f"   [SKIP] 허용되지 않은 도메인: {url[:70]}")
                continue

            print(f"   [CLICK]  클릭 중: {url[:70]}...")
            new_page = None
            try:
                new_page = await context.new_page()
                await new_page.goto(url, wait_until="commit", timeout=30000)
                await new_page.wait_for_load_state("load", timeout=30000)
                await random_delay(DELAY["page_min"], DELAY["page_max"])

                await try_click_participation_button(new_page)

                await human_like_scroll(new_page)
                await random_delay(DELAY["action_min"], DELAY["action_max"])
                await new_page.close()

                visited.add(url)  # 클릭 완료 후 즉시 기록
                clicked_count += 1
                print(f"   [OK] 클릭 완료!")

            except Exception:
                print("   [WARN]  링크 클릭 중 오류가 발생했습니다.")
                if new_page:
                    try:
                        await new_page.close()
                    except Exception:
                        pass

            await random_delay(DELAY["action_min"], DELAY["action_max"])

    except Exception:
        print("   [ERR] 게시글 처리 중 오류가 발생했습니다.")

    return clicked_count


async def try_click_participation_button(page: Page):
    """참여하기 / 적립 신청 버튼을 찾아 클릭합니다."""
    button_texts = [
        "참여하기", "이벤트 참여", "적립 받기", "받기", "신청하기",
        "참여", "포인트 받기", "apply", "participate", "claim",
    ]
    try:
        for text in button_texts:
            for role in ("button", "link"):
                el = page.get_by_role(role, name=text)
                if await el.count() > 0:
                    print(f"   [BTN] '{text}' 버튼 클릭...")
                    await random_delay(0.5, 1.5)
                    await el.first.click()
                    await random_delay(DELAY["action_min"], DELAY["action_max"])
                    print(f"   [OK] 버튼 클릭 완료!")
                    return
    except Exception:
        pass
