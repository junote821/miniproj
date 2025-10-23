# Day2 Local RAG with FAISS

---

## 0) 개요
- **목표**: 로컬 문서만으로 질의에 답하는 **RAG 파이프라인** 구축 (웹검색은 보조)  
- **핵심 구성**: `ingest.py → rag_store.py → agents.py → main.py`  
- **표준 인터페이스**: `FaissStore.load_or_new / upsert / search / ntotal`  
- **표준 반환 스키마**(검색 결과):  
  `{"id","title","url","source","summary","text","page","kind","score"}`

---

## 1) 산출물·경로 표준
```
data/
├─ raw/                      # 입력 원문
└─ processed/
   └─ day2/
      ├─ faiss/
      │  ├─ faiss.index     # FAISS 인덱스
      │  ├─ chunks.jsonl    # 메타(한 줄=1청크, 최소: {"id","text"})
      │  └─ ids.json        # 인덱스 순서 ↔ 청크 id 매핑
      └─ day2_snapshot_instructor.md
```
- 기본 인덱스 경로: `data/processed/day2/faiss` (환경변수로 변경 가능)

---

## 2) 환경변수
| 키 | 기본값 | 설명 |
|---|---|---|
| `MODEL_NAME` | `openai/gpt-4o-mini` | ADK LLM(강사용) |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | 임베딩 모델(LiteLLM) |
| `EMBED_BATCH` | `8` | 임베딩 배치 크기(실패 시 개별 호출 폴백) |
| `D2_INDEX_DIR` | `data/processed/day2/faiss` | 인덱스 저장 디렉터리 |
| `RAG_RAW_DIR` | `data/raw` | 입력 문서 폴더 |
| `D2_QUERY` | `헬스케어 AI 임상 적용 사례 알려줘` | 스모크 테스트 질의 |

---

## 3) 파일별 상세 (메서드 단위)

### A. `day2/instructor/ingest.py` *(참고: main에서 사용; 함수 시그니처 기준 설명)*
> **역할**: 입력 소스 수집 → 텍스트화/청킹 → 청크 메타 JSONL 생성

#### `collect_sources_from_folder(raw_dir: str, allowed_exts: tuple = (".pdf",".txt",".md"), urls_file: str = "urls.txt", recursive: bool = True) -> list[str]`
- **기능**: `raw_dir`에서 허용 확장자의 파일을 재귀 수집하고, `urls.txt`가 있으면 URL도 병합  
- **출력**: 경로/URL 문자열 리스트(중복 제거)  
- **사용처**: `main.main()` 1단계 소스 수집

#### `ingest_sources(paths: list[str], out_dir: str = "data/processed/day2/faiss", chunk_size: int = 800, overlap: int = 100, kind: str | None = None) -> list[dict]`
- **기능**: 경로/URL → 텍스트 로드 → 슬라이딩 윈도우 청킹(800자/100자 겹침) → 청크 메타 작성  
- **메타 필드(권장)**: `{"id","text","title","source","page","kind"}` (최소: `id`,`text`)  
- **부작용**: `{out_dir}/chunks.jsonl`로 저장(라인 단위 JSON)  
- **사용처**: `FaissStore.upsert()` 입력

---

### B. `day2/instructor/rag_store.py`
> **역할**: 로컬 **FAISS** 벡터 스토어. 인덱스/메타/ID 정합성 유지. Day4 라우터가 **RAG-First**로 재사용

#### 전역
- `EMB_MODEL`: 임베딩 모델명(환경변수 `EMBEDDING_MODEL`)
- `DEFAULT_INDEX_DIR`: 인덱스 기본 폴더(`D2_INDEX_DIR`)
- `BATCH`: 배치 임베딩 크기(`EMBED_BATCH`)

#### `def embed_texts(texts: list[str]) -> np.ndarray`
- **입력**: 문자열 리스트  
- **처리**: LiteLLM `embedding(model=EMB_MODEL, input=...)` 배치 호출 → `float32` 배열로 변환 → **L2 정규화**(cosine용)  
- **가드**: 빈 입력은 `(0,1536)` 제로 배열 반환  
- **출력**: `shape=(N, D)` 넘파이 배열

#### `class FaissStore`
- **파일 구조**:  
  `{index_dir}/faiss.index`, `{index_dir}/chunks.jsonl`, `{index_dir}/ids.json`

##### `__init__(index_dir: str | None = None)`
- 경로 세팅 및 폴더 생성. 내부 경로: `index_path`, `meta_path`, `ids_path`

##### `@classmethod load_or_new(index_dir: str | None = None) -> FaissStore`
- 인덱스 유무와 상관없이 **핸들 반환**(지연 로드). Day4에서 선호

##### `@classmethod load(index_dir: str | None = None) -> FaissStore`
- `load_or_new`와 동일한 단순 핸들 생성(호환성)

##### `def upsert(self, chunks: list[dict]) -> tuple[int, int]`
- **입력**: `{"id","text",...}` 형태의 청크 리스트  
- **동작**:
  1) 기존 메타 로드→`id` 기준 병합→`chunks.jsonl` 갱신  
  2) 인덱스/`ids.json` 로드  
  3) **신규 항목만 임베딩 후 `index.add`** (증분)  
  4) 임베딩 차원 변경 등으로 **불일치** 시 **전체 재빌드**  
- **출력**: `(ntotal, n_added)`

##### `def search(self, query: str, k: int = 6) -> list[dict]`
- **입력**: 질의 문자열, top-`k`  
- **처리**: 질의 임베딩→`IndexFlatIP` 검색→`ids.json`으로 id 매핑→`chunks.jsonl` 메타 결합  
- **출력(표준 스키마)**: `[{id,title,url,source,summary,text,page,kind,score}, ...]`  
- **비고**: `k`는 `1..ntotal`로 보정

##### `def ntotal(self) -> int`
- 인덱스의 전체 벡터 수.

##### **Aliases**  
`query(query,k)`, `similarity_search(query,k)`, `search_top_k(query,k)` → 모두 `search`와 동일

##### (내부 도움 메서드)
- `_load_meta() / _save_meta(items)`: `chunks.jsonl` 로드/저장  
- `_load_ids() / _save_ids(ids)`: `ids.json` 로드/저장  
- `_read_index() / _write_index(index)`: `faiss.index` 로드/저장  
- `_build_index_from_meta(meta) -> (index, ids_order)`: 전체 재빌드 유틸

---

### C. `day2/instructor/agents.py`
> **역할**: **RAG 답변 에이전트**(ADK). 컨텍스트 전용 답변 + 인용.

#### 전역
- `MODEL_NAME`: 환경변수, 기본 `openai/gpt-4o-mini`(LiteLLM 통해 ADK 모델 지정)
- `RAG_INST`: 시스템 프롬프트 — “제공된 컨텍스트 외 추측 금지, 간결 한국어, 인용 [refN:제목|URL]”
- `rag_agent = LlmAgent(...)`: 강사용 에이전트 인스턴스

#### `async def _run_once(agent: LlmAgent, text: str) -> str`
- **입력**: 최종 사용자 프롬프트 문자열  
- **동작**: `InMemoryRunner`로 `run_async` 스트림 수신 → 최종 파트 텍스트 반환  
- **가드**: 세션 사전 생성 시 예외 무시(이미 존재)

#### `def answer_with_context(query: str, hits: list[dict], k_refs: int = 3) -> str`
- **입력**: 사용자 질문, 검색 결과(`FaissStore.search` 결과), 인용 수  
- **동작**: 상위 6개 히트를 **불릿 컨텍스트**로 묶고, 상위 `k_refs`로 **인용 리스트** 구성 → `_run_once` 호출
- **출력**: 최종 답변 문자열(인용 포함 기대)

---

### D. `day2/instructor/main.py`
> **역할**: **오케스트레이션**(스모크 테스트 겸 문서화 스냅샷 생성)

#### `def render_hits_table(items: list[dict], title: str = "RAG Retrieval") -> str`
- **동작**: 검색 결과를 마크다운 표로 변환(`#, 제목, 점수, 출처`).

#### `def main() -> None`
1) 소스 수집: `collect_sources_from_folder(RAG_RAW_DIR)`  
2) 인제스트: `ingest_sources(..., kind="healthcare")` → `chunks.jsonl` 생성  
3) 업서트: `FaissStore().upsert(chunks)` → `faiss.index/ids.json` 갱신  
4) 검색: `store.search(query, k=6)` → 표 출력  
5) 생성: `answer_with_context(query, hits)` → 최종 답변 출력  
6) 저장: `data/processed/day2_snapshot_instructor.md` 생성

> 실행: `python -m day2.instructor.main` (또는 리포 구조에 맞춰 `python main.py`)

---

## 4) Day4 라우터 연동 가이드 (RAG-First)
```python
from day2.instructor.rag_store import FaissStore

store = FaissStore.load_or_new("data/processed/day2/faiss")
if store.ntotal() > 0:
    hits = store.search(user_query, k=6)
    # 점수·커버리지 히유리스틱으로 품질 판단
    good = hits and hits[0]["score"] >= 0.25
    if good:
        return answer_with_context(user_query, hits, k_refs=3)
# RAG에 충분한 근거가 없으면 WebSearch로 폴백
return run_web_search_then_write(user_query)
```
- **표준 스키마** 덕분에 Day4의 리포팅/테이블 렌더러가 그대로 재사용

---

## 5) 체크리스트 & 트러블슈팅
- 인덱스 없음: `ntotal()==0` → 인제스트/업서트 선행 필요
- 임베딩 모델 변경: 차원 불일치 감지 시 **자동 전체 재빌드**
- `ids.json` 유실/파손: 검색 결과 매핑 오류 → `upsert(chunks)`로 재생성
- 배치 오류: 외부 API 한도/오류 시 자동 **개별 호출 폴백**
- 속도: `EMBED_BATCH`↑, 중복 소스 제거, 청크 크기 조정(800/100 권장)

---

## 6) 품질 팁
- `title`/`source`를 메타에 충실히 채워두면, 표/인용이 **읽기 쉬움**
- 도메인별 `kind` 태그(예: `"healthcare"`)는 Day4 라우터의 **테마 라우팅**에 유용
- 질문이 구체적일수록 `score` 분포가 선명해져 RAG-First 판단이 쉬워짐
