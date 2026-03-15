# Naver Pay Auto Clicker — AI Agent Reference

> 이 문서는 다른 AI 도구(Gemini CLI, OpenAI Codex, GitHub Copilot 등) 또는
> 다른 PC 환경에서 이 프로젝트를 이어받아 작업할 때 참고하는 기준 문서입니다.
> 마지막 갱신: 2026-03-16

---

## 1. 프로젝트 개요

| 항목 | 내용 |
|------|------|
| 목적 | 뽐뿌 게시판에서 "네이버페이 포인트" 관련 게시글을 탐색하고 본문 내 적립 링크를 자동 클릭 |
| 언어 | Python 3.11+ (현재 환경: Python 3.14.2) |
| 핵심 라이브러리 | `playwright >= 1.58.0` (Chromium 브라우저 자동화) |
| 운영 환경 | Windows 11 (PowerShell / CMD) |
| 인증 방식 | 사용자가 1회 수동 로그인 → `session.json`에 쿠키 저장 → 이후 세션 재사용 |

---

## 2. 파일 구조 및 역할

```
naver-auto-pay/
├── config.py       # 중앙 설정 파일 (URL, 키워드, 딜레이, 보안 화이트리스트)
├── login.py        # 수동 로그인 & session.json 저장 (최초 1회)
├── scraper.py      # 뽐뿌 검색결과 페이지 크롤링 + 날짜 필터링
├── clicker.py      # 게시글 본문에서 적립 링크 수집 & 클릭
├── main.py         # 진입점: 날짜 선택 → 스캔 → 클릭 → 반복 루프
├── diagnose.py     # 선택자/HTML 구조 디버깅용 스크립트 (운영 불필요)
├── requirements.txt
├── setup.bat       # 환경 설치 (pip + playwright browser)
├── login.bat       # login.py 실행 단축
├── run.bat         # main.py 실행 단축
├── session.json    # 네이버 로그인 쿠키 (자동 생성, 커밋 금지)
├── visited.json    # 이미 처리한 URL 목록 (자동 생성, 커밋 금지)
└── AGENTS.md       # 이 파일
```

---

## 3. 실행 순서

```
1. setup.bat          # 최초 1회: pip install + playwright install chromium
2. login.bat          # 최초 1회: 브라우저에서 네이버 로그인 → session.json 생성
3. run.bat            # 매번 실행: 날짜 범위 선택 → 스캔 → 클릭
```

---

## 4. 핵심 설계 결정 (변경 시 주의)

### 4-1. 세션 유지 방식
- `playwright` `storage_state` API 사용
- 저장: `await context.storage_state(path=SESSION_FILE)`
- 로드: `browser.new_context(storage_state=SESSION_FILE)`
- **session.json 에는 쿠키와 localStorage가 평문 저장**됨 → 절대 git에 커밋하지 말 것

### 4-2. 뽐뿌 검색 페이지 구조 (2026-03 기준 확인)
- URL 패턴: `search_bbs.php?page_size=50&...&page_no={N}`
  - 페이지 파라미터: `page_no=` (일반 게시판의 `page=`와 다름)
- HTML 구조 (table 없음, div 기반):
  ```html
  <div class="conts">
    <div class="content">
      <span class="title"><a href="/zboard/view.php?...">제목</a></span>
      <p>본문 미리보기...</p>
      <p class="desc">
        <span>[게시판명]</span>
        <span>조회수: 1234</span> |
        <span>2026.03.15</span>   ← 날짜 (YYYY.MM.DD 형식)
        ...
      </p>
    </div>
  </div>
  ```
- **선택자**: `div.conts div.content` → `span.title a` (제목/링크)
- **날짜 선택자**: `p.desc span` 중 `/^[0-9]{4}[.][0-9]{2}[.][0-9]{2}$/` 패턴

### 4-3. 페이지 이동 방식
```python
# 리다이렉트가 있어도 중단되지 않는 방식
await page.goto(url, wait_until="commit", timeout=30000)
await page.wait_for_load_state("load", timeout=30000)
```
- `wait_until="load"` 또는 `"domcontentloaded"` 단독 사용 시
  뽐뿌의 세션 기반 리다이렉트로 인해 `Navigation interrupted` 에러 발생
- **반드시 commit + wait_for_load_state 조합을 유지할 것**

### 4-4. 날짜 필터링 로직
```
scraper.py:parse_post_date() 지원 형식:
  "HH:MM"      → 오늘
  "YYYY.MM.DD" → 해당 날짜 (뽐뿌 검색결과 실제 형식)
  "YY/MM/DD"   → 해당 날짜
  "YYYY-MM-DD" → 해당 날짜
  "MM-DD"      → 올해
```
- 최신순 정렬 기준으로, 페이지의 가장 오래된 글이 `date_from`보다 이전이면 순회 중단

### 4-5. visited.json 원자적 쓰기
```python
# 데이터 손상 방지: 임시 파일 → os.replace() 패턴
with tempfile.NamedTemporaryFile(...) as tmp:
    json.dump(list(visited), tmp, ...)
    os.fsync(tmp.fileno())
os.replace(tmp_path, VISITED_FILE)
```
- `open("w")` 직접 쓰기 방식으로 되돌리지 말 것 (프로세스 강제 종료 시 데이터 손실)

---

## 5. 보안 정책

### 5-1. URL 화이트리스트
`config.py`의 `ALLOWED_DOMAINS`에 없는 도메인은 `goto()` 호출을 거절함.
```python
ALLOWED_DOMAINS = [
    "ppomppu.co.kr", "pay.naver.com", "naver.me",
    "naver.com", "campaign2.naver.com",
    "m-campaign.naver.com", "ofw.link.naver.com",
]
```
- 새 도메인 추가 시 이 목록에 먼저 추가할 것
- `file://`, `data://`, `javascript:` 스킴은 자동 차단

### 5-2. 패턴 단일 소스
- 네이버페이 링크 패턴은 `config.py`의 `NAVERPAY_LINK_PATTERNS` 하나만 사용
- `clicker.py`는 이를 import해서 사용 (`NAVERPAY_PATTERNS = NAVERPAY_LINK_PATTERNS`)
- 별도로 패턴 목록을 정의하지 말 것

### 5-3. 예외 처리 정책
- `except Exception as e: print(e)` 형태 금지 (스택/경로 정보 노출)
- 사용자 출력은 일반 메시지만: `print("오류가 발생했습니다.")`
- 상세 원인이 필요하면 별도 로그 파일로 저장할 것

### 5-4. 민감 파일
| 파일 | 내용 | 주의 |
|------|------|------|
| `session.json` | 네이버 로그인 쿠키 전체 | **git 커밋 금지**, chmod 600 적용됨 |
| `visited.json` | 방문한 URL 목록 | git 커밋 불필요 |

---

## 6. 설정 변경 가이드

### 게시판 추가
`config.py`의 `BOARDS` 리스트에 항목 추가:
```python
{"name": "게시판명", "url": "https://...", "pages": 50}
```
- `pages`는 안전 상한선 (날짜 범위 도달 시 자동 중단되므로 50 권장)
- 뽐뿌 URL이면 자동으로 `page_no=` 파라미터 사용
- 새 도메인이면 `ALLOWED_DOMAINS`에도 추가 필요

### 키워드 추가
`config.py`의 `KEYWORDS` 리스트에 추가:
```python
KEYWORDS = ["네이버페이", "naver pay", "naverpay", "네이버 페이", "적립"]
```

### 딜레이 조정
`config.py`의 `DELAY` 딕셔너리에서 수정:
```python
DELAY = {
    "action_min": 1.5,  "action_max": 4.0,   # 클릭 사이
    "page_min":   3.0,  "page_max":   8.0,   # 페이지 이동 후
    "post_min":   2.0,  "post_max":   5.0,   # 게시글 열기 전
}
```
- **최소값을 1.0 이하로 낮추지 말 것** (차단 위험)

### 네이버페이 링크 패턴 추가
`config.py`의 `NAVERPAY_LINK_PATTERNS`에 추가:
```python
NAVERPAY_LINK_PATTERNS = [
    "ofw.link.naver.com",
    "campaign2.naver.com",
    ...
]
```
- 추가하는 도메인은 `ALLOWED_DOMAINS`에도 함께 추가할 것

---

## 7. 주요 트러블슈팅 히스토리

| 증상 | 원인 | 해결 |
|------|------|------|
| `Navigation interrupted` 에러 | `wait_until="load"` 사용 시 뽐뿌 세션 리다이렉트와 충돌 | `wait_until="commit"` + `wait_for_load_state("load")` 분리 |
| `게시글을 하나도 읽지 못했습니다` | 뽐뿌 검색결과가 `<table>` 없이 `<div class="conts">` 구조 사용 | JS 선택자를 `div.conts div.content > span.title a`로 변경 |
| `page_no=` 파라미터 무시 | `&page=1` 추가 시 뽐뿌가 마지막 방문 페이지로 리다이렉트 | `search_bbs.php`인 경우 `page_no=` 파라미터 사용 |
| `session.json` 미생성 | `input()`이 asyncio 이벤트 루프를 블록해 브라우저 연결 끊김 | `loop.run_in_executor(None, input, msg)`로 비블로킹 처리 |
| 이모지 출력 에러 `UnicodeEncodeError` | Windows CMD 기본 인코딩 CP949가 이모지 미지원 | `sys.stdout.reconfigure(encoding="utf-8")` + 이모지 → ASCII 기호 |
| 날짜 파싱 실패 | 뽐뿌 검색결과 날짜 형식이 `YYYY.MM.DD` (점 구분자) | `parse_post_date()`에 `"%Y.%m.%d"` 형식 추가 |

---

## 8. 코딩 컨벤션

- **print 태그 형식**: `[OK]`, `[WARN]`, `[ERR]`, `[INFO]`, `[SKIP]`, `[SCAN]`, `[PAGE]`, `[LINK]`, `[CLICK]`, `[BTN]`, `[DATE]`, `[RESULT]`, `[NEW]`, `[STOP]`
- **비동기**: 모든 브라우저 조작은 `async/await` 사용
- **딜레이**: 직접 `asyncio.sleep()` 대신 `random_delay(min, max)` 래퍼 사용
- **파일 경로**: 절대경로 고정 (`config.py`의 `_BASE_DIR` 기준)
- **예외**: 사용자 출력에 원본 예외 메시지 포함 금지

---

## 9. 절대 하지 말아야 할 것

1. `session.json`을 git에 커밋하거나 외부에 공유하지 말 것
2. `wait_until="load"` 단독 사용 (리다이렉트 충돌)
3. `open(VISITED_FILE, "w")` 직접 쓰기 (원자성 없음)
4. `except Exception as e: print(e)` (민감 정보 노출)
5. `DELAY` 최소값을 1.0초 미만으로 설정 (차단 위험)
6. `ALLOWED_DOMAINS`에 없는 도메인을 `goto()`로 직접 열기
7. `page.evaluate(f"...{python_var}...")` 형태의 f-string JS 인젝션

---

## 10. 의존성

```
playwright >= 1.58.0   # Chromium 브라우저 자동화
  └─ greenlet >= 3.1.1  # Python 3.14 호환 빌드 필요
  └─ pyee >= 13.0.0

Python 표준 라이브러리만 그 외 사용:
  asyncio, json, os, random, re, stat, sys, tempfile,
  datetime, urllib.parse
```

설치:
```bash
pip install -r requirements.txt
python -m playwright install chromium
```
