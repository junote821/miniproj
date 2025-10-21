"""
역할: 수집된 raw item들을 공통 스키마로 정규화하고, 중복 제거
TODO 포인트:
- (선택) 스키마 필드 확장
- (선택) 중복 기준 강화
"""

import hashlib
from typing import List, Dict

def _id(url: str, title: str) -> str:
    base = (url or "") + "|" + (title or "")
    return hashlib.md5(base.encode("utf-8")).hexdigest()

def normalize_items(items: List[Dict], kind: str) -> List[Dict]:
    """TODO-1: 필요시 스키마에 필드를 더 추가해보세요(예: category, region 등)"""
    out = []
    for it in items:
        out.append({
            "id": _id(it.get("url",""), it.get("title","")),
            "title": (it.get("title") or "").strip(),
            "url": (it.get("url") or "").strip(),
            "summary": (it.get("snippet") or it.get("summary") or "").strip(),
            "date": it.get("date"),
            "kind": kind,
            "source": it.get("source") or kind,
            "announce_date": it.get("announce_date"),
            "close_date": it.get("close_date"),
            "agency": it.get("agency"),
            "budget": it.get("budget"),
            "attachments": it.get("attachments") or [],
            "requirements": it.get("requirements"),
            "content_type": it.get("content_type","text"),
            "text_len": it.get("text_len", 0),
            "attach_cnt": it.get("attach_cnt", 0),
        })
    return out

def deduplicate(items: List[Dict]) -> List[Dict]:
    """TODO-2: 중복 기준을 강화
    예) url 같거나 title 유사도 > 0.9인 경우 제거 (현재는 url|title md5만 사용)
    """
    seen, res = set(), []
    for it in items:
        if it["id"] in seen:
            continue
        seen.add(it["id"])
        res.append(it)
    return res
