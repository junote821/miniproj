# Day3 TODO 체크리스트

## 목표

* NIPA 사업공고를 **수집 → 정규화/중복 제거 → 간단 랭킹 → Digest 생성**까지 완성
* **텍스트형**은 본문 요약(불릿), **첨부형**은 첨부 링크 중심
* 결과물:

  * `data/processed/day3_snapshot_student.md` (요약 리포트)
  * `data/processed/day3_notices_student.json` (라우터 입력용)

## 파일 구조(학생용)

* ✔ `day3/student/parsers.py` — **완성 템플릿(수정 불필요)**
* ✔ `day3/student/fetchers.py` — **완성 템플릿(수정 불필요)**
* ✏ `day3/student/normalize.py` — **간단 TODO**
* ✏ `day3/student/agents.py` — **간단 TODO(요약 규칙 튜닝)**
* ✏ `day3/student/main.py` — **핵심 TODO(키워드/랭킹/Digest)**

> 실행:
>
> ```bash
> NIPA_MAX_PAGES=1 NIPA_MAX_ITEMS=8 NIPA_MIN_YEAR=2024 \
> python -m day3.student.main
> ```

---

## TODO A–D: 정규화/중복 제거 (난이도: 하)

**파일**: `day3/student/normalize.py`

* **TODO-1** `normalize_items`

  * 스키마 확장(선택): 예) `category`, `region`, `tags` 등 필드 추가
  * 출력은 최소 `{id,title,url,summary,date,kind,source,announce_date,close_date,agency,budget,attachments,requirements,content_type}` 유지
* **TODO-2** `deduplicate`

  * 현재는 `md5(url|title)` 기준
  * (선택) 제목 유사도 등 보강 아이디어 주석으로 남기기

**완료 기준**

* 중복 항목이 눈에 띄게 줄고, 필드 누락 없이 일관된 스키마를 유지

---

## TODO E–H: 요약 에이전트 튜닝 (난이도: 하)

**파일**: `day3/student/agents.py`

* **TODO-3** `TEXT_SUM_INST` 프롬프트 튜닝

  * 불릿 개수, 금지어, 길이(“한 줄당 20자 내외” 등) 팀별로 지정
  * 불명확 시 “공고문 확인 필요” 유지
* **TODO-4** `summarize_text_points`

  * (선택) 빈 텍스트 처리/리턴 포맷 조정
  * (선택) 숫자/영문 섞인 문장 가독성 개선(예: 콜론 이후 줄바꿈)

**완료 기준**

* 텍스트형 공고에 대해 3~5개 **간결한 한국어 불릿**이 안정적으로 생성

---

## TODO I–N: 오케스트레이션/랭킹/Digest (난이도: 중)

**파일**: `day3/student/main.py`

* **TODO-A** `extract_keywords`

  * 불용어 보강, 숫자·영문 토큰 처리 개선
  * (선택) 중복 토큰 축약(“ai”, “인공지능” → 하나로)
* **TODO-B** `keyword_score`

  * 단순 포함 → **정규식 경계(`\b`)** 적용해 정밀도 향상
  * 첨부 파일명 가중(+0.3 가점 등) 추가
* **TODO-C** `render_digest`

  * `matched_fields` 표기는 **옵션**: 필요하면 숨기기 또는 키워드만 굵게
  * 텍스트형: 요약 불릿 강조 / 첨부형: 링크 목록 강조
  * (선택) 소제목/메타(공고일/마감/기관/예산) 배치 개선
* **TODO-D** 랭킹 가중치 조정

  * 기본: `score = 0.7*keyword + 0.3*recency`
  * 팀별로 0.6/0.4, 0.5/0.5 등 변경 후 결과 비교
  * 최근성은 `announce_date` 기준으로 2024/2025 가점

**완료 기준**

* Top-15 표에서 점수가 들어오고, 질의와 관련된 항목이 상단
* Digest 섹션이 **한눈에 읽기 좋고**(텍스트/첨부 구분 명확), 메타 필드가 정리됨

---

## (선택) 확장 과제 — RAG/하이라이트/UI (난이도: 중~상, 선택)

* **RAG 연결**

  * Day2의 `FaissStore`를 가져와 `to_rag_chunks()` 구현 후 업서트/검색
  * Retrieval 표(Top-K)와 최종 답변(근거 링크 포함)을 하단에 추가
* **키워드 하이라이트**

  * Digest 내부 제목/요약/첨부 파일명에서 매칭 키워드를 **굵게** 표시
* **UI 레이아웃**

  * 표 + 카드형 블록 혼합(텍스트형: 카드, 첨부형: 리스트)
  * 항목 수 제한·정렬 옵션 `.env`로 노출

---

## 시간 배분 가이드(총 6h)

1. **오리엔테이션/실행 확인** (0.5h)

   * .env 설정/실행, 결과 파일 생성 확인
2. **키워드/랭킹 튜닝** (1.5h)

   * TODO-A/B/D: 키워드 추출·점수·가중치 조정 → Top-15 품질 개선
3. **Digest 레이아웃 개선** (1.0h)

   * TODO-C: 텍스트/첨부 구분 렌더링 다듬기
4. **정규화/중복 제거 보강** (0.5h)

   * TODO-1/2: 스키마·중복 기준 개선
5. **요약 프롬프트/스타일 튜닝** (1.0h)

   * TODO-3/4: 팀별 톤앤매너, 길이 제한 등
6. **개별 팀 심화/테스트/정리** (1.5h)

   * (선택) RAG/하이라이트/연도 필터 튜닝, 케이스 테스트 및 문서화

---

## 트러블슈팅

* **“주요사업” 같은 메뉴성 페이지만 뜸**

  * `NIPA_MAX_PAGES` ↑, `NIPA_MIN_YEAR=2025`로 최신 공고 필터
  * 키워드 가중 상향, 첨부 파일명 가중 추가
* **요약이 반복되거나 애매함**

  * `TEXT_SUM_INST`에 금지/권장 규칙 명시, 불릿 개수와 길이 제한
* **첨부형이 많아 텍스트가 거의 없음**

  * 첨부형 섹션을 상단 배치, 첨부 표시 개수 확대(최대 8~10개)

---

### 주의

* **parsers/fetchers는 수정하지 않습니다.** (완성 템플릿)
* 시간이 남으면 RAG/하이라이트/UI 확장을 도전하세요.
