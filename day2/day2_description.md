# 전체 개념도 (Day2 — 로컬 RAG + 보조 WebSearch)

**핵심 포인트**

1. `main.py`의 `smoke_ingest_and_qa()`가 **오케스트레이션**
2. **폴더 자동 스캔 → 인제스트(텍스트화/청크) → 임베딩/FAISS 업서트 → 검색 → RAG QA** 순으로 호출
3. Retrieval 결과(로컬 문서) **표시 + 인용 포함 답변** 생성, (옵션) Day1 **WebSearch 표**도 함께 출력
4. URL 본문 파싱은 **BeautifulSoup(단순 추출)**, PDF는 **pypdf**, 임베딩은 **litellm.embedding**, 인덱스는 **FAISS**
5. 결과/산출물은 `data/processed/day2/`에 **재활용 가능한 형태(chunks.jsonl, faiss.index)** 로 저장

---


# 파일별 상세 설명 (메서드 단위)

## 1) `day2/ingest.py`

### `def read_text_from_pdf(path: str) -> str`

* **역할**: PDF 페이지 텍스트 추출
* **입력**: 파일 경로
* **처리**: `pypdf.PdfReader`로 페이지 루프 → `extract_text()` 합치기 (실패 페이지는 빈 문자열)
* **출력**: 문자열(문서 전체 텍스트)
* **연결**: `read_text_auto()` 내부에서 확장자에 따라 호출

### `def read_text_from_url(url: str, timeout: int) -> str`

* **역할**: URL HTML → 텍스트(간단 크롤링)
* **입력**: URL
* **처리**: `requests.get`(+User-Agent) → `BeautifulSoup` → `script/style` 제거 → `get_text(" ", strip=True)` → 공백 정규화
* **출력**: 문자열(본문 텍스트)
* **연결**: `read_text_auto()`에서 URL일 때

### `def read_text_auto(src: str) -> Dict`

* **역할**: **파일/URL 자동 판별** 후 텍스트와 메타 생성
* **입력**: 파일경로 또는 URL
* **처리**: PDF/일반텍스트/URL 분기 → 텍스트 수집, 메타 `{source,type,title}`
* **출력**: `{"text": <str>, "meta": {...}}`
* **연결**: `ingest_sources()`에서 호출

### `def chunk_text(text: str, chunk_size=800, overlap=200) -> List[str]`

* **역할**: **슬라이딩 윈도우 청킹**
* **입력**: 본문 문자열
* **처리**: 공백 정규화 → 800자 기준, 200자 겹침 → 빈 청크 제거
* **출력**: 문자열 리스트(청크들)
* **연결**: `ingest_sources()`

### `def ingest_sources(sources: List[str], out_dir: str) -> List[Dict]`

* **역할**: 소스들을 읽어 **청크+메타**를 만들고 **저장**
* **입력**: 파일/URL 목록, 출력 디렉토리
* **처리**: 각 소스 → `read_text_auto` → `chunk_text` → 청크마다 `id=md5(source::idx)` 부여 → `chunks.jsonl` 저장
* **출력**: `[{id,text,source,page,kind,title}, ...]`
* **연결**: `main.py` → `FaissStore.upsert()`로 전달

---

## 2) `day2/rag_store.py`

### `def embed_texts(texts: List[str]) -> np.ndarray`

* **역할**: 텍스트 → 임베딩 행렬
* **입력**: 텍스트 리스트
* **처리**: `litellm.embedding(model=EMB_MODEL, input=t)` 반복 → `np.array(float32)`
* **출력**: `shape=(N,D)` 행렬
* **연결**: `upsert()`, `search()`

### `class FaissStore`

#### `__init__(dirpath: str)`

* **역할**: 경로 세팅
* **처리**: `self.index_path=faiss.index`, `self.meta_path=chunks.jsonl`, (강사용) `self.ids_path=ids.json`
* **연결**: 아래 메서드들이 이 경로에 저장/로드

#### `def upsert(self, chunks: List[Dict]) -> Tuple[int, int]`

* **역할**: 인덱스 **빌드/갱신**
* **전략**:

  * **재빌드(기본)**: 기존 메타와 병합 → 전체 임베딩 → 새 `IndexFlatIP(d)` 생성 → `add` → 저장
  * **증분(선택)**: 기존 id 목록을 저장/로드하여 **새 id만 임베딩 → add**, 차원 불일치면 재빌드
* **출력**: `(index.ntotal, 이번에 추가한 개수)`
* **연결**: `main.py`에서 인제스트 후 호출

#### `def search(self, query: str, k=5) -> List[Dict]`

* **역할**: 질의 벡터화 후 **Top-k 검색**
* **처리**: 인덱스 로드 → 질의 임베딩/정규화 → `index.search` → `chunks.jsonl`에서 메타 조합 → `score` 추가
* **출력**: `[{... , score: float}, ...]`
* **연결**: `main.py`에서 QA 컨텍스트로 사용

---

## 3) `day2/agents.py`

### `ragqa_agent = LlmAgent(...)`

* **역할**: **RAG QA 전담 에이전트**
* **프롬프트 규칙**:

  * “근거 컨텍스트로만 답변”
  * 문장 끝 인용: `[refN:제목|출처]` 최대 3개

### `async def _run_once(agent, sys_prompt, user_prompt) -> str`

* **역할**: **Runner**로 1회 실행(최종 응답 텍스트 수집)
* **입력**: 시스템/사용자 프롬프트
* **출력**: 최종 답변 텍스트
* **연결**: `answer_with_context()`

### `def answer_with_context(question: str, chunks: List[Dict], k_refs=3) -> str`

* **역할**: **Top-k 컨텍스트**를 조립하여 **인용 포함 답변** 생성
* **입력**: 질문, 검색 히트
* **처리**:

  1. 상위 `k_refs` 청크로 컨텍스트 블록 구성
     `"[1] {title}\n{text}\n\n[2] ..."`
  2. `_run_once` 호출
  3. (안전망) 인용이 없으면 최소 1개 ref 부착
* **출력**: 답변 문자열


---

## 4) `day2/main.py`

### `collect_sources_from_folder(raw_dir, allowed_exts, urls_file, recursive) -> list[str]`

* **역할**: 폴더 내 **pdf/txt/md 전체 재귀 수집** + `urls.txt`의 URL까지 병합
* **출력**: **파일 경로/URL 리스트**(중복 제거)

### `def render_hits_table(hits) -> str`, `def render_web_table(results) -> str`

* **역할**: **Retrieval / WebSearch 결과 표**(markdown) 생성

### `def smoke_ingest_and_qa()`

* **역할**: **오케스트레이션**
* **처리 순서**:

  1. 폴더 자동 스캔(파일/URL 열거)
  2. `ingest_sources` → `chunks.jsonl` 생성
  3. `FaissStore.upsert` → `faiss.index` 갱신
  4. `FaissStore.search(question)` → Retrieval 표 출력
  5. (옵션) `WebSearchTool.run(question)` → Web 표 출력
  6. `answer_with_context(question, hits)` → 인용 포함 **답변**(강사용은 스트리밍 가능)
  7. `data/processed/day2_snapshot.md` 저장

---

# 데이터 단위 (입/출력)

| 함수/메서드                               | 입력          | 출력                                           | 비고                  |          |
| ------------------------------------ | ----------- | -------------------------------------------- | ------------------- | -------- |
| `read_text_from_pdf(path)`           | 파일경로        | `str` 텍스트                                    | pypdf               |          |
| `read_text_from_url(url)`            | URL         | `str` 텍스트                                    | BeautifulSoup       |          |
| `read_text_auto(src)`                | 파일경로/URL    | `{"text": str, "meta": {...}}`               | type/title 포함       |          |
| `chunk_text(text)`                   | `str`       | `List[str]`                                  | 800자/200자 overlap   |          |
| `ingest_sources(sources)`            | 파일/URL 리스트  | `List[Dict{id,text,source,page,kind,title}]` | + `chunks.jsonl` 저장 |          |
| `embed_texts(texts)`                 | `List[str]` | `np.ndarray(float32, shape=(N,D))`           | litellm.embedding   |          |
| `FaissStore.upsert(chunks)`          | 청크 리스트      | `(ntotal:int, added:int)`                    | + `faiss.index` 저장  |          |
| `FaissStore.search(query, k)`        | 질의, k       | `List[Dict{..., score:float}]`               | 메타 조합               |          |
| `answer_with_context(question,hits)` | 질문, 검색결과    | `str`(인용 포함 답변)                              | `[refN:title        | source]` |
| `smoke_ingest_and_qa()`              | -           | 콘솔/`day2_snapshot.md`                        | 전체 오케스트레이션          |          |

---

# 체크 포인트

1. **인제스트 성공**: `[INGEST SOURCES]`에 파일/URL이 나열되고, `chunks.jsonl` 라인 수 > 0
2. **인덱스 구축**: `faiss.index` 생성, 콘솔에 `FAISS total: N, added: M`
3. **검색 히트**: Retrieval 표에 Top-k가 점수와 함께 표시
4. **답변 품질**: 본문에 **근거 인용** `[refN:제목|출처]`가 붙어 있음
5. **보고서 저장**: `data/processed/day2_snapshot.md` 생성 (Retrieval/Web 표 + 답변)

---
