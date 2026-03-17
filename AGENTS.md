# Naver Pay Auto Clicker — AI Agent Reference

> 이 문서는 다른 AI 도구(Gemini CLI, OpenAI Codex, GitHub Copilot 등) 또는
> 다른 PC 환경에서 이 프로젝트를 이어받아 작업할 때 참고하는 기준 문서입니다.
> 마지막 갱신: 2026-03-17 (오늘만 탐색 옵션 추가 및 문서 전면 보완)

---

## 1. 프로젝트 개요

| 항목 | 내용 |
|------|------|
| 목적 | 뽐뿌 게시판에서 "네이버페이 포인트" 관련 게시글을 탐색하고 본문 내 적립 링크를 자동 클릭 |
| 언어 | Python 3.11+ (현재 환경: Python 3.12) |
| 핵심 라이브러리 | `playwright >= 1.58.0` (Chromium 브라우저 자동화) |
| 운영 환경 | Windows 11 (PowerShell / CMD) |
| 인증 방식 | 사용자가 1회 수동 로그인 → `session.json`에 쿠키 저장 → 이후 세션 재사용 |

---

## 2. 파일 구조 및 역할

```
naver-auto-pay-master/
├── config.py       # 중앙 설정 파일 (URL, 키워드, 딜레이, 보안 화이트리스트)
├── login.py        # 수동 로그인 & session.json 저장 (최초 1회)
├── scraper.py      # 뽐뿌 검색결과 페이지 크롤링 + 날짜 필터링
├── clicker.py      # 게시글 본문에서 적립 링크 수집 & 클릭 (선택자 강화)
├── main.py         # 진입점: 날짜 선택 → 스캔 → 클릭 → 반복 루프
├── requirements.txt
├── setup.bat       # 환경 설치 (pip + playwright browser)
├── login.bat       # login.py 실행 단축
├── run.bat         # main.py 실행 단축
├── session.json    # 네이버 로그인 쿠키 (자동 생성, 커밋 금지)
├── visited.json    # 이미 처리한 URL 목록 (자동 생성, 커밋 금지)
└── AGENTS.md       # 이 파일
```

---

## 3. 실행 흐름

```
run.bat
  └─ main.py
       ├─ session.json 존재 확인 (없으면 종료)
       ├─ visited.json 로드
       ├─ Playwright Chromium 브라우저 실행 (headless=False)
       └─ [반복 루프]
            ├─ select_date_range()  ← 날짜 범위 선택 (5가지 옵션)
            ├─ scan_once()
            │    ├─ scraper.py → scrape_ppomppu_board() / scrape_generic_board()
            │    │    └─ 날짜 필터 + 키워드 매칭 → 게시글 목록 반환
            │    └─ clicker.py → find_and_click_naverpay_links()
            │         ├─ collect_links_from_post()  ← 3단계 링크 수집
            │         ├─ is_safe_url() 검증
            │         └─ try_click_participation_button()  ← 참여 버튼 클릭
            └─ 계속/종료 선택
```

### 날짜 범위 선택 옵션 (main.py: select_date_range)

| 옵션 | 설명 | 반환 범위 |
|------|------|-----------|
| 1 | 오늘만 | today ~ today |
| 2 | 오늘 ~ 1일 전 | today-1 ~ today |
| 3 | 오늘 ~ 3일 전 | today-3 ~ today |
| 4 | 오늘 ~ 1주일 전 | today-7 ~ today |
| 5 | 직접 입력 | 최대 7일 범위, 90일 이전 불가 |

**직접 입력(옵션 5) 제약:**
- 미래 날짜 입력 불가
- 90일 이전 날짜 입력 불가
- 범위가 7일 초과 시 종료일 기준 7일 전으로 시작일 자동 조정
- 종료일 비워두면 오늘로 자동 설정

---

## 4. 핵심 설계 결정 (변경 시 주의)

### 4-1. 세션 및 접속 보안
- `playwright` `storage_state` API 사용
- **Anti-Blocking**: 뽐뿌의 봇 차단(`ERR_EMPTY_RESPONSE`)을 피하기 위해 `main.py`에서 표준 `User-Agent`를 강제 설정함.
  ```python
  user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
  ```
- **브라우저 보안 설정** (`main.py` context 생성 시):
  ```python
  ignore_https_errors=False   # HTTPS 인증서 오류 불허
  permissions=[]              # 모든 브라우저 권한 거절
  # launch args: --disable-extensions, --disable-plugins, --mute-audio
  ```

### 4-2. 뽐뿌 검색 페이지 구조 (2026-03 기준 확인)
- URL 패턴: `search_bbs.php?bbs_cate=2&keyword={ENCODED_KEYWORD}`
- **목록 선택자**: `div.conts div.content` → `span.title a` (제목/링크)
- **날짜 추출**: `p.desc` 안의 `span` 중 `YYYY.MM.DD` 패턴 (정규식 매칭)

### 4-3. 페이지 이동 방식
```python
# 리다이렉트가 있어도 중단되지 않는 방식
await page.goto(url, wait_until="commit", timeout=30000)
await page.wait_for_load_state("domcontentloaded", timeout=30000)
```
- **`"commit"`**: 응답 헤더 수신 즉시 반환 → 리다이렉트가 일어나도 `Navigation interrupted` 없음
- **`"domcontentloaded"`**: HTML DOM 파싱 완료 시점에 반환. 뽐뿌는 광고/외부 트래킹 스크립트가 완료되지 않아 `"load"` 이벤트가 영원히 발화하지 않으므로 반드시 `"domcontentloaded"` 사용
- **적용 범위**: `scrape_ppomppu_board()`와 `clicker.py` 모두 이 방식 사용
- **예외**: `scrape_generic_board()`는 현재 `wait_until="load"` 단독 사용 중.
  리다이렉트 없는 일반 게시판 전용이므로 현재는 문제없으나, 뽐뿌 외 사이트 추가 시 `"commit"` + `"domcontentloaded"` 방식으로 수정 필요.

### 4-4. 게시글 본문 선택자 (clicker.py: collect_links_from_post)
뽐뿌의 다양한 테이블/디브 구조 대응을 위해 아래 목록을 순서대로 순회:
```javascript
const bodySelectors = [
    'div.board-contents',   // 주로 사용
    'td.board-contents',
    'div.view_content',
    'td.board_content',
    'div.post-content',
    'div.view-content',
    'div#content',          // 추가 폴백
    'td#content',           // 추가 폴백
];
// 위 선택자 모두 실패 시 → document.body 전체에서 탐색
```

### 4-5. 적립 링크 수집 3단계 전략 (clicker.py: collect_links_from_post)
게시글 하나당 3단계로 링크를 수집한 뒤 중복 제거 → 네이버페이 패턴 필터링:

| 단계 | 방법 | 비고 |
|------|------|------|
| 1 | 본문 `<a href>` 태그 수집 | 가장 기본적 |
| 2 | 본문 텍스트에서 URL 정규표현식 추출 (`URL_REGEX`) | 링크 태그 없이 텍스트로만 적힌 URL 대응 |
| 3 | 첨부 링크 영역 (`div.attach a`, `.link_list a`, "링크1/링크2" 텍스트 버튼) | 뽐뿌 스타일 첨부 링크 대응 |

### 4-6. 참여 버튼 자동 클릭 (clicker.py: try_click_participation_button)
네이버페이 적립 링크 페이지 진입 후 아래 텍스트의 버튼/링크를 자동 탐색하여 클릭:
```python
button_texts = [
    "참여하기", "이벤트 참여", "적립 받기", "받기", "신청하기",
    "참여", "포인트 받기", "apply", "participate", "claim",
]
```
- `page.get_by_role("button" | "link", name=text)` 방식 사용
- 버튼 클릭 후 `action_min ~ action_max` 딜레이 적용
- 첫 번째로 매칭되는 버튼 클릭 즉시 반환 (중복 클릭 방지)

### 4-7. 사람 같은 스크롤 (clicker.py: human_like_scroll)
링크 클릭 전/후로 마우스 휠 스크롤 3~6회 (200~500px 랜덤), 각 0.3~0.8초 간격.
봇 감지 우회 목적이므로 제거하지 말 것.

### 4-8. visited.json 원자적 쓰기 (main.py: save_visited)
데이터 손상 방지를 위해 직접 쓰지 않고 임시 파일 경유:
```python
# tempfile.NamedTemporaryFile → json.dump → os.fsync → os.replace (atomic)
```
Windows에서도 `os.replace()`는 원자적으로 동작함.
저장 완료 후 파일 권한을 소유자 읽기/쓰기 전용으로 제한.

### 4-9. 자동 페이지 탐색 중단 (scraper.py: scrape_ppomppu_board)
`max_pages=50`은 무한 루프 방지 상한선이며, 실제로는 다음 조건에서 즉시 중단:
- 페이지 내 **가장 오래된 게시글 날짜 < 시작일**이면 다음 페이지 탐색 불필요로 판단
- 게시글이 0개인 페이지 도달 시 중단

---

## 5. config.py 설정 항목 요약

```python
BOARDS                  # 크롤링 대상 게시판 목록 (name, url, pages)
KEYWORDS                # 매칭할 키워드 목록 (소문자 비교)
DELAY                   # 딜레이 설정 (action / page / post 구분)
SESSION_FILE            # session.json 절대경로
VISITED_FILE            # visited.json 절대경로
NAVERPAY_LINK_PATTERNS  # 네이버페이 URL 패턴 목록 (clicker.py와 공유)
ALLOWED_DOMAINS         # goto() 허용 도메인 화이트리스트
```

현재 `ALLOWED_DOMAINS`:
```
ppomppu.co.kr, pay.naver.com, naver.me, naver.com,
campaign2.naver.com, m-campaign.naver.com, ofw.link.naver.com
```

새 도메인 추가 시 `ALLOWED_DOMAINS`와 `NAVERPAY_LINK_PATTERNS` 양쪽 모두 확인할 것.

---

## 6. 설정 변경 가이드

### 딜레이 조정 (사람다운 패턴)
`config.py`의 `DELAY` 딕셔너리에서 수정:
```python
DELAY = {
    "action_min": 2.0,  "action_max": 4.5,   # 클릭 사이
    "page_min":   3.0,  "page_max":   5.0,   # 페이지 이동 후 (사용자 요청: 3~4초 텀)
    "post_min":   3.0,  "post_max":   6.0,   # 게시글 열기 전
}
```
- 페이지 탐색 시 너무 빠른 호출로 인한 차단을 막기 위해 최소 3초 이상의 텀을 유지함.

---

## 7. 주요 트러블슈팅 히스토리

| 증상 | 원인 | 해결 |
|------|------|------|
| `Navigation interrupted` 에러 | `wait_until="load"` 사용 시 뽐뿌 세션 리다이렉트와 충돌 | `wait_until="commit"` + `wait_for_load_state("domcontentloaded")` 분리 (clicker.py 포함 전역 적용) |
| 페이지 스캔 30초 타임아웃 (`[WARN] N페이지 스캔 중 오류`) | 뽐뿌 페이지의 광고/외부 트래킹 스크립트가 응답하지 않아 `"load"` 이벤트가 영원히 발화하지 않음 | `wait_for_load_state("load")` → `wait_for_load_state("domcontentloaded")`로 전환 (scraper.py, clicker.py 전체) |
| `net::ERR_EMPTY_RESPONSE` | 헤드리스 브라우저/기본 UA 사용 시 뽐뿌가 접속 차단 | `main.py`에 실제 크롬 `User-Agent` 문자열 추가 |
| `적립 링크 발견 못함` | 뽐뿌 게시글 본문 컨테이너가 `view_content` 또는 `board_content`인 경우 존재 | `clicker.py`의 `bodySelectors`에 해당 선택자들 추가 |
| `탐색 속도가 너무 빠름` | `DELAY` 설정이 낮아 사람 같지 않음 | `page_min`을 3.0으로 상향 조정하여 페이지당 3~5초 대기 강제 |
| 날짜 파싱 실패 | 뽐뿌 검색결과 날짜 형식이 `YYYY.MM.DD` (점 구분자) | `parse_post_date()`에 `"%Y.%m.%d"` 형식 추가 |

---

## 8. 모듈별 주요 함수 레퍼런스

| 파일 | 함수 | 역할 |
|------|------|------|
| `main.py` | `select_date_range()` | 콘솔 UI로 날짜 범위 선택 (5가지 옵션) |
| `main.py` | `scan_once()` | 전체 게시판 1회 스캔 |
| `main.py` | `save_visited()` | visited.json 원자적 저장 |
| `main.py` | `is_safe_url()` | 도메인 화이트리스트 URL 검증 |
| `scraper.py` | `scrape_ppomppu_board()` | 뽐뿌 전용 크롤러 (날짜 자동 중단 포함) |
| `scraper.py` | `scrape_generic_board()` | 일반 게시판 크롤러 (날짜 필터) |
| `scraper.py` | `parse_post_date()` | 날짜 문자열 파싱 (HH:MM / YYYY.MM.DD / YY/MM/DD / YYYY-MM-DD / MM-DD) |
| `clicker.py` | `find_and_click_naverpay_links()` | 게시글 열기 + 링크 수집 + 클릭 총괄 |
| `clicker.py` | `collect_links_from_post()` | 3단계 링크 수집 |
| `clicker.py` | `try_click_participation_button()` | 적립 참여 버튼 자동 클릭 |
| `clicker.py` | `human_like_scroll()` | 봇 감지 우회용 사람 같은 스크롤 |
| `login.py` | `manual_login()` | 수동 로그인 & session.json 저장 |

---

## 9. 절대 하지 말아야 할 것

1. `session.json`을 git에 커밋하거나 외부에 공유하지 말 것
2. `wait_until="load"` 단독 사용 — `scrape_ppomppu_board()`와 `clicker.py`는 반드시 `"commit"` + `wait_for_load_state` 분리 방식 사용
3. **User-Agent를 제거하거나 기본값으로 되돌리기** (뽐뿌 차단 위험)
4. `open(VISITED_FILE, "w")` 직접 쓰기 (원자성 없음 → `save_visited()` 함수 사용)
5. `DELAY` 최소값을 1.0초 미만으로 설정 (차단 위험)
6. `ALLOWED_DOMAINS` 외의 도메인을 무검증으로 `goto()` 하기
