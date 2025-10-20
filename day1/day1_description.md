# 전체 개념도

* **핵심 포인트**:

  1. `main.py`의 `smoke_run()`이 오케스트레이션
  2. **분류 → 검색 → URL 요약** 순으로 Tool/Agent를 호출
  3. URL 본문 요약은 **(Firecrawl → 실패 시 requests)** 로 텍스트를 가져오고, **SummarizerAgent**가 5문장 요약

---

# 파일별 상세 설명 (메서드 단위)

## 1) `src/day1/*/agents.py`

### `summarizer_agent = Agent(...)`

* **역할**: LLM에게 “요약자” 역할 지시(정확히 5문장 요약 등 규칙)
* **입력**: `UserContent(parts=[Part.from_text(text)])`
* **출력**: `Agent.run()` 결과(LLM 응답 오브젝트; `.text`로 텍스트 접근)
* **연결**: `summarize_text()`에서 사용

### `def summarize_text(text: str) -> str`

* **역할**: **텍스트 → 5문장 요약**을 수행하는 **실행 함수**
* **입력**: `text: str`
* **처리**:

  1. `UserContent(parts=[Part.from_text(text)])` 생성
  2. `summarizer_agent.run(content)` 호출
  3. `.text`를 안전하게 추출(`getattr(result, "text", "")`)
* **출력**: `str`(요약 텍스트)
* **연결**: `SummarizeUrlTool.run()` 내부에서 URL 본문 요약 시 호출

---

### `classifier_agent = Agent(...)`

* **역할**: LLM에게 “도메인 분류자” 역할 지시(Healthcare/ICT/Energy/Etc 중 택1)
* **입력**: `UserContent(parts=[Part.from_text(text)])`
* **출력**: `Agent.run()` 결과(라벨 텍스트)
* **연결**: `classify_topic()`에서 사용

### `def classify_topic(text: str) -> str`

* **역할**: **텍스트 → 도메인 라벨**(Healthcare/ICT/Energy/Etc)
* **입력**: `text: str`
* **처리**:

  1. `classifier_agent.run()` 호출 → LLM 라벨 텍스트 받기
  2. 라벨을 소문자/키워드 포함 여부로 **보정**(강사용은 더 많은 키워드)
* **출력**: 정규화된 라벨 문자열
* **연결**: `main.py`에서 사용자 질의의 **의도/도메인 표기**로 사용

> 참고) **멀티모달 확장**: `event.content.parts` 배열에 `Part.from_image(...)` 등 이미지/파일 파트를 추가 가능(현재는 텍스트만 사용).

---

## 2) `src/day1/*/tools.py`

### `class WebSearchTool(AgentTool)`

* **역할**: **Tavily API**를 통해 **웹 검색 결과(제목/URL/스니펫) 리스트** 반환
* **주요 속성**:

  * `name = "web_search"`: Router/AgentTool 호출 시 식별자
  * `self.api_key`: `.env`에서 `TAVILY_API_KEY` 읽기
  * `self.top_k`: 반환 개수 제한
* **핵심 메서드**: `def run(self, query: str) -> List[Dict[str, str]]`

  * **입력**: `query: str` (사용자 질의)
  * **처리**:

    1. API 키 없으면 **MOCK 결과** 반환
    2. 있으면 `POST https://api.tavily.com/search` 호출
    3. 응답 JSON에서 상위 `top_k`를 골라 `{title, url, snippet}`으로 정리
    4. 예외 시 **FALLBACK 항목** 1개 반환
  * **출력**: `[{title, url, snippet}, ...]`

---

### `class SummarizeUrlTool(AgentTool)`

* **역할**: **URL 본문을 가져와 요약**(Firecrawl → 실패 시 `requests.get`)
* **주요 속성**:

  * `name = "summarize_url"`
  * `self.summarize_fn`: 외부에서 `summarize_text()` **함수 주입** (의존성 역전)
  * `self.fc_key`: `.env`의 `FIRECRAWL_API_KEY`
  * `self.max_chars`: 너무 긴 본문을 잘라 요약 품질/속도 유지
* **핵심 메서드**: `def run(self, url: str) -> Dict[str, Any]`

  * **입력**: `url: str`
  * **처리**(우선순위):

    1. **Firecrawl** 사용 가능(키 있음) → `POST /v1/scrape`로 `markdown/rawText` 요청
    2. 실패/키 없음 → **폴백**: `requests.get(url)` 후 HTML 그대로 텍스트 슬라이스
    3. `self.summarize_fn(text)`로 요약 호출(= `summarize_text`)
  * **출력**: `{"url": url, "summary": <요약 텍스트>}`


---

## 3) `src/day1/*/main.py`

### `def smoke_run(user_query: str)`

* **역할**: **Day 1 스모크 테스트 오케스트레이션**
* **입력**: `user_query: str`(사용자 질의)
* **처리 순서**:

  1. `classify_topic(user_query)` → **도메인 라벨**
  2. `WebSearchTool(top_k=3).run(user_query)` → **상위 결과 리스트**
  3. 첫 번째 결과의 `url`로 `SummarizeUrlTool(summarize_text).run(url)` → **본문 요약**

---

# 데이터 단위(입·출력)

| 함수/메서드                      | 입력    | 출력                              | 비고                                       |
| --------------------------- | ----- | ------------------------------- | ---------------------------------------- |
| `summarize_text(text)`      | `str` | `str`(5문장 요약)                   | `summarizer_agent.run()` 내부 호출           |
| `classify_topic(text)`      | `str` | `str`(라벨)                       | `classifier_agent.run()` 내부 호출           |
| `WebSearchTool.run(query)`  | `str` | `List[Dict{title,url,snippet}]` | Tavily 호출, 키 없으면 MOCK                    |
| `SummarizeUrlTool.run(url)` | `str` | `Dict{url, summary}`            | Firecrawl 우선 → GET 폴백 → `summarize_text` |
| `smoke_run(user_query)`     | `str` | 콘솔/파일                           | 오케스트레이션                                  |

---

# 체크 포인트

1. **Agent는 “역할/규칙 프롬프트 + run(content)”**로 구성 → `event.content.parts`에 텍스트/이미지 파트 추가 가능
2. **Tool은 외부 I/O(HTTP)·전처리** 담당 → 요약/분류는 **Agent가 수행**
3. **의존성 주입**: `SummarizeUrlTool(summarize_text)`처럼 함수 포인터 주입 → 테스트/교체 쉬움
4. **키 없어도 실행 가능(MOCK/FALLBACK)** → 실습 안정성 확보

---
