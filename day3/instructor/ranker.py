import os, numpy as np, re
from typing import List, Dict
from litellm import embedding
from day3.instructor.parsers import compute_days_left

EMB_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

GENERIC_TITLE = {"주요사업","사업안내","사업 안내"}

def _embed_one(t: str) -> np.ndarray:
    r = embedding(model=EMB_MODEL, input=t or "")
    v = np.array(r["data"][0]["embedding"], dtype="float32")
    v = v / (np.linalg.norm(v) + 1e-9)
    return v

def _embed_many(texts: List[str]) -> np.ndarray:
    vecs=[_embed_one(t) for t in texts]
    return np.stack(vecs, axis=0)

def _keyword_score(item: Dict, keywords: List[str]) -> float:
    STOP = {"사업","공고","모집","지원","안내","찾아줘","최신","최근"}
    blob = f"{item.get('title','')} {item.get('summary') or item.get('snippet','')}".lower()
    atts = " ".join([(a.get("name") or "") for a in (item.get("attachments") or [])]).lower()
    text = blob + " " + atts
    ks = [k for k in keywords or [] if k and k not in STOP]
    if not ks: return 0.0
    s=0.0
    for k in ks:
        if re.search(rf"\b{re.escape(k)}\b", text): s += 1.0
        elif k in text: s += 0.5
    return min(1.0, s/len(ks))

def rank_notices(query: str, items: List[Dict], keywords: List[str],
                 w_deadline: float = 0.6, w_sim: float = 0.25, w_kw: float = 0.15) -> List[Dict]:
    if not items: return []
    # 의미유사도
    Q = _embed_one(query)
    texts = [(it.get("title","")+" "+(it.get("summary") or it.get("snippet",""))).strip() for it in items]
    X = _embed_many(texts)
    sim = (X @ Q)

    # 마감 임박
    dl = np.array([compute_days_left(it.get("close_date")) for it in items], dtype="float32")
    dl_norm = np.zeros_like(dl)
    for i, d in enumerate(dl):
        if np.isnan(d): dl_norm[i] = 0.15
        else:
            if d < 0: dl_norm[i] = 0.0
            elif d >= 30: dl_norm[i] = 0.0
            else: dl_norm[i] = (30 - d) / 30.0  # 0일→1.0

    # 키워드
    kw = np.array([_keyword_score(it, keywords) for it in items], dtype="float32")

    total = w_deadline*dl_norm + w_sim*sim + w_kw*kw

    # 메뉴성 제목 패널티
    for i, it in enumerate(items):
        if it.get("title","").strip() in GENERIC_TITLE and not it.get("attachments"):
            total[i] *= 0.6

    order = np.argsort(-total)
    ranked=[]
    for idx in order:
        it = dict(items[idx])
        it["score_deadline"] = float(dl_norm[idx])
        it["score_sim"] = float(sim[idx])
        it["score_kw"] = float(kw[idx])
        it["score"] = float(total[idx])
        ranked.append(it)
    return ranked
