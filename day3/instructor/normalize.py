import hashlib
from typing import List, Dict

def _id(url:str, title:str)->str:
    base = (url or "") + "|" + (title or "")
    return hashlib.md5(base.encode("utf-8")).hexdigest()

def normalize_items(items: List[Dict], kind: str) -> List[Dict]:
    out=[]
    for it in items:
        out.append({
            "id": _id(it.get("url",""), it.get("title","")),
            "title": it.get("title","").strip(),
            "url": it.get("url","").strip(),
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
    seen, res=set(), []
    for it in items:
        if it["id"] in seen: continue
        seen.add(it["id"]); res.append(it)
    return res
