"""
학생용 랭커 모듈.
- 키워드 기반 OR 스코어 + 최근성 가점만으로 간단 정렬
- 외부 임베딩/라이브러리 없이 동작
- main.py의 extract_keywords()와 동일한 규칙으로 keywords를 받아서 사용

확장 아이디어(TODO):
- 키워드 정규식 경계(\b) 적용
- 첨부 파일명 가중 강화
- 날짜 가점 함수를 선형 → 로그/지수 스케일 등으로 변경
"""

import os
from typing import List, Dict

def _keyword_or_score(item: Dict, keywords: List[str]) -> float:
    blob = f"{item.get('title','')} {item.get('summary','')}".lower()
    atts = " ".join([(a.get('name') or "") for a in (item.get('attachments') or [])]).lower()
    text = blob + " " + atts
    if not keywords:
        return 0.0
    s = 0.0
    for k in keywords:
        if not k:
            continue
        # TODO: 정규식 경계(\b)로 정밀도 향상해보기
        if k in text:
            s += 1.0
    return min(1.0, s / max(1, len(keywords)))

def _recency_bonus(item: Dict, base_year: int) -> float:
    """announce_date가 base_year 이상이면 가점(0.3 기본). 더 세밀하게 확장 가능."""
    ad = item.get("announce_date")
    if not ad or len(ad) < 4:
        return 0.0
    try:
        y = int(ad[:4])
    except Exception:
        return 0.0
    return 0.3 if y >= base_year else 0.0

def rank_items(query: str, items: List[Dict], keywords: List[str],
               w_kw: float = 0.7, w_recency: float = 0.3,
               base_year: int = None) -> List[Dict]:
    """
    간단 랭킹:
      score = w_kw * keyword_or + w_recency * recency_bonus
    반환: score가 부여되고 내림차순 정렬된 아이템 리스트
    """
    if base_year is None:
        base_year = int(os.getenv("NIPA_MIN_YEAR", "2024"))

    ranked = []
    for it in items:
        kw = _keyword_or_score(it, keywords)      # 0~1
        rec = _recency_bonus(it, base_year)       # 0 또는 0.3
        it = dict(it)  # 원본 보호
        it["score"] = w_kw * kw + w_recency * rec
        ranked.append(it)

    ranked.sort(key=lambda x: x.get("score", 0.0), reverse=True)
    return ranked
