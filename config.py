# ======================================================
# config.py - 설정 파일
# ======================================================

import os

# 프로젝트 루트 기준 절대경로 (경로 조작 방지)
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ----- 크롤링할 게시판 목록 -----
BOARDS = [
    {
        "name": "뽐뿌 네이버페이 검색",
        "url": "https://www.ppomppu.co.kr/search_bbs.php?bbs_cate=2&keyword=%B3%D7%C0%CC%B9%F6%C6%E4%C0%CC+%C6%F7%C0%CE%C6%AE",
        "pages": 50,  # 날짜 범위 도달 시 자동 중단 (최대 안전 한도)
    },
]

# ----- 검색할 키워드 (소문자로 비교합니다) -----
KEYWORDS = ["네이버페이", "naver pay", "naverpay", "네이버 페이", "적립"]

# ----- 딜레이 설정 (초 단위) -----
DELAY = {
    "action_min": 2.0,
    "action_max": 4.5,
    "page_min": 3.0,
    "page_max": 5.0,
    "post_min": 3.0,
    "post_max": 6.0,
}

# ----- 파일 경로 (절대경로 고정) -----
SESSION_FILE = os.path.join(_BASE_DIR, "session.json")
VISITED_FILE = os.path.join(_BASE_DIR, "visited.json")

# ----- 네이버페이 적립 링크 패턴 (clicker.py와 공유) -----
# 허용된 도메인 외 URL은 열지 않습니다.
NAVERPAY_LINK_PATTERNS = [
    "ofw.link.naver.com",
    "campaign2-api.naver.com",
    "campaign2.naver.com",
    "m-campaign.naver.com",
    "naver.me/",
    "new-m.pay.naver.com",
    "external-token.pay.naver.com/entry",
    "home.pay.naver.com/?from=",
    "point.pay.naver.com",
    "pay.naver.com",
]

# goto() 허용 도메인 화이트리스트 (이 도메인 이외의 URL은 열지 않음)
ALLOWED_DOMAINS = [
    "ppomppu.co.kr",
    "pay.naver.com",
    "naver.me",
    "naver.com",
    "campaign2.naver.com",
    "m-campaign.naver.com",
    "ofw.link.naver.com",
]
