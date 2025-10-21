import os, numpy as np
from typing import List, Dict
from litellm import embedding

EMB_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

def _embed(texts: List[str]) -> np.ndarray:
    vecs = []
    for t in texts:
        r = embedding(model=EMB_MODEL, input=t)
        vecs.append(r["data"][0]["embedding"])
    X = np.array(vecs, dtype="float32")
    X = X / (np.linalg.norm(X, axis=1, keepdims=True) + 1e-9)
    return X

def rank_items(query: str, items: List[Dict], w_sim: float = 0.6, w_recency: float = 0.4) -> List[Dict]:
    if not items: return []
    texts = [(it.get("title","")+" "+it.get("summary","")).strip() for it in items]
    Q = _embed([query])[0]
    X = _embed(texts)
    sim = X @ Q
    rec = np.array([1.0 if it.get("date") else 0.0 for it in items], dtype="float32")
    total = w_sim*sim + w_recency*rec
    order = np.argsort(-total)
    ranked = []
    for idx in order:
        it = dict(items[idx]); it["score"] = float(total[idx]); ranked.append(it)
    return ranked
