아래는 **이번 세션 전체 작업 총정리**입니다. 그대로 `KT-AIVLE-miniproject-summary.md`로 저장해 두면, 새 세션에서도 빠르게 이어갈 수 있어요. 덧붙여, 제가 핵심 컨텍스트를 “기억”하도록 설정했으니(위에 저장됨), 새 세션에서 “KT AIVLE 미니프로젝트 계속” 정도로 말해주시면 바로 이 구성을 바탕으로 이어갈 수 있어요.

---

# KT AIVLE — Google ADK 코드-퍼스트 미니프로젝트 총정리

## 프로젝트 개요

* **목표**: 도메인 Q&A/분석(헬스케어·ICT 등), **웹검색**+**로컬 RAG**+**정부 공고 수집**을 조합한 **종합 에이전트 시스템** 구축.
* **구성**: 4일 과정

  * **Day1**: 웹검색(Tavily) & URL 요약(Firecrawl→`requests` 폴백), 간단 분류 Agent
  * **Day2**: 로컬 RAG(FAISS) — **RAG-first** 설계, 표준 인터페이스
  * **Day3**: 정부 공고(현재 **NIPA**만) 수집 → 정규화/중복제거/랭킹 → **텍스트형/첨부형 분기 요약**
  * **Day4**: **Router/Planner**로 Day1/Day2/Day3 도구를 조합 실행 + 가드레일

---

## 핵심 원칙

1. **RAG-first**: Day4는 로컬 KB를 먼저 조회(프리플라이트). 컨텍스트 부족 시만 웹검색 폴백.
2. **호환 표준화**: RAG 저장소는

   * `FaissStore.load_or_new(index_dir)`
   * `FaissStore.upsert(chunks)`
   * `FaissStore.search(query, k)`
     인터페이스를 제공(파일 3종: `faiss.index`, `chunks.jsonl`, `ids.json`).
3. **안전 폴백**: 외부 의존(Firecrawl, Tavily) 실패 시 **requests/단순 HTML 추출**로 폴백.
4. **가드레일**: Router가 **정부 공고** 도구는 특정 키워드/확신도 조건에서만 사용.

---

## Day1 (웹검색 & 요약)

### 기능

* **WebSearchTool**: Tavily API로 `{title,url,snippet}` 리스트 반환(키 없으면 MOCK).
* **SummarizeUrlTool**: Firecrawl `/scrape` 우선 → 실패 시 `requests.get()` → 텍스트 최대 길이 제한 후 **SummarizerAgent**로 **5문장 요약**.
* **ClassifierAgent**: 간단 도메인 분류(Healthcare/ICT/Energy/Etc).

### 실행

```bash
python -m day1.instructor.main
```

* 출력: `data/processed/day1_snapshot.md`
* 흐름: **분류 → 검색 → 1건 URL 요약**

---

## Day2 (로컬 RAG — FAISS)

### 학생용(TODO) 스켈레톤 제공

* `day2/student/rag_store.py`

  * **TODO-D2-1~6**: 임베딩(L2 정규화)·인덱스·검색·표준 스키마
* `day2/student/ingest.py`

  * **TODO-D2-7~10**: 파일 수집→텍스트→청크→업서트
* `day2/student/agents.py`

  * **TODO-D2-11**: 인용 포함 간단 답변 포맷
* `day2/student/main.py`

  * **TODO-D2-12,14**: Retrieval 표 렌더 + 스모크 실행/저장

### 강사용(해답) 주안점

* `FaissStore`는 **IndexFlatIP + L2 정규화**.
* **차원 불일치 시 전체 재빌드** 로 단순·안정화.
* 반환 스키마(표준):

  ```json
  {"id","title","url","source","summary","text","page","kind","score"}
  ```

### 실행

```bash
python -m day2.student.ingest
D2_QUERY="AI 규제" python -m day2.student.main
```

* 인덱스 위치(기본): `data/processed/day2/faiss`
* 스냅샷: `data/processed/day2_snapshot.md`

---

## Day3 (정부 공고 — NIPA 크롤러)

### 기능

* **목록 수집**: `NIPA_LIST_URL`의 페이징된 목록 → 상세 링크 필터(`/home/2-2/<id>`).
* **상세 수집**: Firecrawl `/scrape`로 **markdown/rawText/links** 확보 → 실패 시 `requests+BS4` 폴백.
* **정규화/중복제거**: `{id,title,url,summary,date/kind/source,attachments,content_type}` 표준화.
* **랭킹**: (기본) 키워드 단순 매칭 + 최신성 가중치; Top-N 선택.
* **텍스트형/첨부형 분기 요약**:

  * 텍스트 중심: 본문 요약 + (있으면) 첨부 링크 나열
  * 첨부 중심: 첨부 링크 목록 + 메타(공고/마감/기관/예산)

### 실행 (예)

```bash
# 빠른 테스트 환경변수 예
NIPA_MAX_PAGES=1 NIPA_MAX_ITEMS=5 NIPA_PER_ITEM_BYTES=900 \
python -m day3.instructor.main
```

* 출력:

  * **랭킹 표**: 상위 공고 목록
  * **Digest**: 텍스트형/첨부형 섹션
  * (선택) RAG upsert & 질의까지 연계
* 스냅샷: `data/processed/day3_snapshot.md`

### 개선사항 반영

* 상세 페이지에서 **본문/첨부 구분** 로직 보강.
* 질의 키워드를 **강제 AND**하지 않고 **OR + 최근성**으로 랭킹 튜닝.
* 오래된 컨텐츠 우선 문제 → `base_year`(예: 2025) 가중치 반영.

---

## Day4 (Router/Planner + 브릿지 + 포맷터)

### Router(프롬프트) — 핵심 규칙

* 사용할 수 있는 도구:

  * `day1.research(query, top_n?, summarize_top?)`
  * `day2.rag(query, k?)`
  * `day3.government(query, pages?, items?, base_year?)`
* **정부 도구 가드레일**(중요):

  * (A) 질의에 다음 키워드 포함: `["사업공고","공고","입찰","모집","조달","공모","NIPA","정부과제"]`
  * (B) intent=government & 확신도 ≥ 0.7
    → 조건 불만족 시 **day3.government 포함 금지**.
* 출력 JSON:

  ```json
  {"plan":[{"tool":"...","params":{...}},...],
   "final_output":"research_report"|"government_proposal",
   "reasons":["...","..."]}
  ```

### Tools Bridge(호환 레이어)

* **Day1**: 검색+요약 래핑 → `report_md`/`citations`.
* **Day2**: `FaissStore` **여러 구현과 호환**

  * open: `load_or_new` → `load` → 생성자 순
  * search: `search` → `query` → `retrieve` 순
  * ntotal: `ntotal()` → `count()` → `len()` → `index.ntotal`
* **Day3**: 함수명 변동 감안(`fetch_nipa_list_by_query` vs `fetch_nipa_list`) → **try-import**.

### Preflight (RAG-first)

* Router plan이 비어도 **의도 기반 fallback** 동작.
* RAG 인덱스가 있고 컨텍스트 충분 → RAG 우선 사용.
* 예외/부족 시 → **웹검색 폴백**.

### 실행

```bash
python -m day4.instructor.main
# 또는
D4_QUERY="헬스케어 AI 규제 최신 동향 요약해줘" python -m day4.instructor.main
```

* 결과: `data/processed/day4_final_snapshot.md`

---

## .env 주요 변수

```
# 공통
OPENAI_API_KEY=...
TAVILY_API_KEY=...        # 없으면 MOCK
FIRECRAWL_API_KEY=...     # 없으면 requests 폴백
EMBEDDING_MODEL=text-embedding-3-small

# Day1
D1_TOPN=5
D1_SUMM_TOP=2

# Day2
D2_INDEX_DIR=data/processed/day2/faiss
EMBED_BATCH=8

# Day3
NIPA_LIST_URL=https://www.nipa.kr/home/2-2
NIPA_MAX_PAGES=1
NIPA_MAX_ITEMS=10
NIPA_PER_ITEM_BYTES=900
NIPA_MIN_YEAR=2025

# Day4
GOV_KEYWORDS=사업공고,공고,입찰,모집,조달,공모,NIPA,정부과제
GOV_CONF_MIN=0.7
D3_ITEMS=8
D4_HYBRID_RAG=0
```

---

## 학생용 자료(TODO) 정리

* **Day2**: `day2_todo.md` + TODO 주석 포함 스켈레톤 4파일

  * rag_store(임베딩/인덱스/검색), ingest(수집→청크), agents(간단 답변), main(표 렌더+스모크)
* **Day3**: `day3_todo.md` + fetchers/normalize/ranker/agents/main 분해 TODO

  * NIPA 크롤링(목록→상세), 폴백, 정규화/중복 제거, 랭킹, Digest/리포팅

---

## 스모크 테스트 요약

* **Day1**: `python -m day1.instructor.main`
* **Day2**:

  * `python -m day2.student.ingest`
  * `D2_QUERY="..." python -m day2.student.main`
* **Day3**:

  * `NIPA_MAX_PAGES=1 NIPA_MAX_ITEMS=5 python -m day3.instructor.main`
* **Day4**:

  * `D4_QUERY="..." python -m day4.instructor.main`

---

## 트러블슈팅 요약

* **상대/절대 임포트**: 패키지 루트에서 `python -m dayX.instructor.main` 형태로 실행.
* **환경변수 경로**: `.env`는 **레포 루트**에 두고, `load_dotenv(find_dotenv())`.
* **FAISS 불러오기 실패**: Day2 인덱스 **한 번 이상 upsert** 필요.
* **RAG가 비어 웹 폴백되는 경우**: `data/raw`에 문서 추가 후 Day2 인제스트 재실행.
* **NIPA 오래된 문서만**: `NIPA_MIN_YEAR=2025`로 랭킹 가중치 조정.
* **정부 도구 오남용**: Router 가드레일(키워드/확신도) 유지.

---

## 남은 작업 / Day4 확장 아이디어

* **최종 출력 스키마**:

  * `research_report`(Day1/2 기반): Executive summary / Findings / Citations
  * `government_proposal`(Day3 기반): Notices Table / 요구사항 요약 / 제안 초안
* **멀티모달 생성 도구 추가(확장)**:

  * 제안서 초안에 필요한 **캠페인 이미지/짧은 영상** 생성을 별도 AgentTool로 추가
  * Router에 “홍보/캠페인/포스터/이미지” 키워드 감지 시 선택적으로 호출
* **adk web** UI 구동 시** Day4 Router** 연결(프롬프트/툴 디스패치 일체화)

---

## 새 세션에서 이어하는 법

* 이 파일(`KT-AIVLE-miniproject-summary.md`)을 프로젝트 루트에 두세요.
* 새 채팅에서 **“KT AIVLE 미니프로젝트 계속”** 혹은 **“Day4 라우터 마저 진행”** 같이 말해 주세요.
* 제가 **세션 메모리**에도 핵심 맥락(4일 구성, RAG-first 정책, NIPA 크롤러, Router 가드레일)을 저장해두었습니다. 새 세션에서도 이 컨텍스트로 바로 이어갈 수 있어요.

---
