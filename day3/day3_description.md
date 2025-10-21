# `day3_file_description.md` — 파일별/메서드별 설명

## 1) `day3/instructor/parsers.py`

### `parse_dates(text) -> (announce_date, close_date)`

* **역할**: 본문에서 **공고일/마감일** 추출
* **로직**:

  1. “접수기간/신청기간/…” 라벨 **근접 NEAR 글자 내**에서 **날짜 2개**를 찾으면 `(start, end)` 반환
  2. 없을 경우 “마감일/접수마감…” 및 “공고일/게시일…” 라벨 근접에서 **최신 날짜**를 각각 추출
  3. `MIN_YEAR`(예: 2024/2025) 미만은 무시
* **출력**: `"YYYY-MM-DD"` 또는 `None`

### `parse_agency(text) -> Optional[str]`

* **역할**: **기관명** 라벨(주관/전담/수행 등) 뒤 60자 내 한 줄 추출

### `parse_budget(text) -> Optional[str]`

* **역할**: **예산/지원규모**
* **로직**: 금액(숫자+단위) 패턴 우선, 없으면 예산 라벨 뒤 40자 추출

### `parse_requirements(text) -> Optional[str]`

* **역할**: **핵심 요구사항** 후보
* **로직**: “지원대상/신청자격/제출서류/평가기준/사업내용…” **주변 window**에서 **가장 긴 문장** 1개(최대 400자)

### `parse_attachments(links) -> List[Dict]`

* **역할**: `pdf/hwp/hwpx/docx/xlsx/zip…` 확장자 필터로 **첨부 목록** 구조화
* **출력**: `[{name, url}, ...]`

---

## 2) `day3/instructor/fetchers.py`

### `map_nipa_links(list_url, max_pages) -> List[str]`

* **역할**: 목록 페이지에서 **상세 공고 URL**만 수집
* **처리**: Firecrawl `map` → 실패 시 HTML 파싱으로 `a[href]` 추출 → 정규식으로 `/home/2-2/\d+`만 채택

### `_extract_title_from_html(html) -> Optional[str]`

* **역할**: 상세 페이지의 **실제 공고 타이틀** 우선 추출
* **처리**: `div.view-tit h2`, `div.board-view h2`, `article h2`, `h1/h2` → `og:title` → `<title>`

### `_extract_main_text(html) -> str`

* **역할**: **메뉴/푸터 제거**, **메인 컨테이너만** 텍스트 추출
* **처리**: `div.view-cont`, `div.board-view`, `article`, `#contents`, `main` 등에서 **가장 긴 본문**

### `scrape_detail(url, body_limit=900) -> Dict`

* **역할**: 상세 페이지 1건 수집 + 구조화
* **처리**:

  1. Firecrawl `scrape(markdown+links+html)` → 실패 시 `requests.get`
  2. 타이틀/본문 보정(위 두 헬퍼 사용)
  3. `parse_*`로 `announce/close/agency/budget/requirements/attachments` 추출
  4. **콘텐츠 타입 판별**: `attach_cnt>=3` 또는 `text_len<300` ⇒ `"attachment"` else `"text"`
* **출력**: `{"title","url","snippet","announce_date","close_date","agency","budget","requirements","attachments","content_type","text_len","attach_cnt",...}`

### `fetch_nipa_list(list_url, max_pages, body_limit) -> List[Dict]`

* **역할**: 맵/스크레이프를 묶은 **상위 함수**
* **출력**: 상세 아이템 리스트

---

## 3) `day3/instructor/normalize.py`

### `normalize_items(items, kind) -> List[Dict]`

* **역할**: 키 일관화 및 기본 필드 추가
* **포함 필드**: `id, title, url, summary, date, kind, source, announce_date, close_date, agency, budget, attachments, requirements, content_type, text_len, attach_cnt`

### `deduplicate(items) -> List[Dict]`

* **역할**: `md5(url|title)`로 **중복 제거**

---

## 4) `day3/instructor/agents.py`

### `summarize_text_points(text) -> str` *(학생/강사 공통 이름; 강사용은 내부 instruction 강화 가능)*

* **역할**: 텍스트형 공고의 **핵심 포인트(3~5)** 불릿 요약
* **입력**: 본문 텍스트(혹은 `summary`)
* **출력**: 불릿 문자열(한국어)

### `render_digest(items, query_keywords) -> str`

* **역할**: 최종 **Digest(Markdown)** 생성
* **로직**:

  * `content_type == "text"` 그룹: **메타(공고/마감/기관/예산)** + **요약 불릿** + **첨부**
  * `"attachment"` 그룹: **첨부 링크 중심**(+요약 있으면 한 줄)
  * `matched_fields`를 백틱으로 표시

---

## 5) `day3/instructor/main.py`

### `extract_keywords(q, top_n=6) -> List[str]`

* **역할**: 질의에서 **핵심 키워드** 산출(간단 불용어 제거)
* **출력**: 최대 `top_n` 토큰

### `keyword_score(item, keywords) -> float`

* **역할**: **키워드 OR 매칭** 점수(0~1) — 제목/요약/첨부 파일명에서 일치 여부로 가산

### `annotate_matches(items, keywords) -> items`

* **역할**: 각 아이템에 `matched_fields` 주석(`title/summary`, `attachments.name`) 추가

### `to_rag_chunks(items, kind) -> List[dict]`

* **역할**: Day2 RAG 스토어 업서트용 청크 빌드(제목+요약, url 등)

### `render_table(items, title) -> str`

* **역할**: 콘솔/MD 테이블 표시 (Top-N 랭킹 확인용)

### `main()`

* **파이프라인 실행 총괄**

  1. 질의/키워드 추출
  2. `fetch_nipa_list`로 수집
  3. `normalize → deduplicate → (연도필터) → rank_items`
  4. `keyword_score` 가산 + 메뉴 타이틀 하향 + `annotate_matches`
  5. (옵션) RAG 업서트/검색
  6. `render_digest`로 요약/첨부 분기 결과 생성
  7. **저장**: `data/processed/day3_snapshot.md`, `day3_notices.json`

---