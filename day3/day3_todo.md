# Day3 TODO 체크리스트

## 목표

* NIPA 사업공고를 **수집 → 정규화/중복 제거 → 랭킹 → Digest 생성**까지 완성
* **텍스트형**은 본문 요약(불릿), **첨부형**은 첨부 링크 중심
* 결과물:

  * `data/processed/day3_snapshot_student.md`
  * `data/processed/day3_notices_student.json`

## 파일 구성(학생용)

* ✔ `day3/student/parsers.py` — **완성 템플릿(수정 불필요)**
* ✔ `day3/student/fetchers.py` — **완성 템플릿(수정 불필요)**
* ✏ `day3/student/normalize.py` — **간단 TODO**
* ✏ `day3/student/agents.py` — **요약 규칙 튜닝 TODO**
* ✏ `day3/student/ranker.py` — **신규(간단 랭커 모듈)**
* ✏ `day3/student/main.py` — **오케스트레이션/키워드/랭킹/Digest TODO**

---

## TODO A–D: 정규화/중복 제거（난이도: 하）

**파일**: `day3/student/normalize.py`

* **TODO-1** `normalize_items`

  * (선택) 스키마 확장: `category`, `region`, `tags` 등
  * 최소 필드 유지: `{id,title,url,summary,date,kind,source,announce_date,close_date,agency,budget,attachments,requirements,content_type}`
* **TODO-2** `deduplicate`

  * 현재는 `md5(url|title)` 기준
  * (선택) 제목 유사도 등 보강 아이디어 주석으로 남기기

**완료 기준**: 중복이 줄고 필드 일관성 유지

---

## TODO E–F: 요약 에이전트 튜닝（난이도: 하）

**파일**: `day3/student/agents.py`

* **TODO-3** `TEXT_SUM_INST` 프롬프트 튜닝

  * 불릿 개수/길이, 금지어, 톤앤매너 조정
* **TODO-4** `summarize_text_points`

  * (선택) 빈 텍스트 처리/결과 포맷 조정

**완료 기준**: 텍스트형 공고 불릿 요약이 간결·일관

---

## TODO G–K: 키워드/랭킹/Digest（난이도: 중）

**파일**: `day3/student/main.py`, `day3/student/ranker.py`

* **TODO-A** `extract_keywords` (main.py)

  * 불용어 보강, 숫자·영문 토큰 처리 개선
  * (선택) 유사 토큰 통합(예: “ai”/“인공지능”)
* **TODO-B** `keyword_score` (ranker.py 개선 후보 또는 main.py의 annotate 용)

  * 단순 포함 → **정규식 경계 `\b`** 적용 검토
  * 첨부 파일명 가중(+0.3 등) 옵션 고려
* **TODO-C** **랭커 사용으로 대체** (main.py)

  1. 상단에 임포트 추가

     ```python
     from day3.student.ranker import rank_items
     ```
  2. 수동 점수 계산 루프 **삭제** 후 아래로 교체

     ```python
     ranked = rank_items(
         query, pool, q_keywords,
         w_kw=0.7, w_recency=0.3,
         base_year=int(os.getenv("NIPA_MIN_YEAR","2025"))
     )
     ranked = annotate_matches(ranked, q_keywords)
     ```
* **TODO-D** `render_digest` (main.py)

  * `matched_fields` 표기 여부 조정(숨기기/간결화)
  * 텍스트형: 요약 불릿 강조 / 첨부형: 링크 강조
  * (선택) 표/카드형 혼합 레이아웃

**완료 기준**:
Top-15 표에 점수 표시, 질의 관련 항목이 상단 / Digest 가독성↑

---

## 선택 과제: 하이라이트·RAG 연동（난이도: 중~상）

* **키워드 하이라이트**: 제목/요약/첨부 파일명에서 매칭 키워드 **굵게**
* **RAG 연동**: Day2 `FaissStore`를 가져와 `to_rag_chunks()` 구현 → 업서트/검색 → Retrieval 표/근거 인용 추가

---

## 실행 가이드

```bash
# 권장 스모크
NIPA_MAX_PAGES=1 NIPA_MAX_ITEMS=8 NIPA_MIN_YEAR=2025 \
python -m day3.student.main
```

**체크**

* 콘솔에 `Query keywords:` / `Ranked … (Top-15)` 출력
* `data/processed/day3_snapshot_student.md`와 `day3_notices_student.json` 생성

---

## 트러블슈팅

* **메뉴성 “주요사업”만 상단**: `NIPA_MAX_PAGES`↑, `NIPA_MIN_YEAR=2025`, 키워드 가중 상향
* **요약 반복/애매**: 요약 프롬프트 규칙 명확화(불릿 수·길이 제한)
* **첨부형 비중↑**: 첨부 섹션을 위로, 링크 표시수 확대
