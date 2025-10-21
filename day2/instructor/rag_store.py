import os, json, faiss, numpy as np
from typing import List, Dict, Tuple, Optional
from litellm import embedding

EMB_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
PROCESSED_DIR = os.getenv("RAG_PROCESSED_DIR", "data/processed/day2")

# ---------------- Embedding ----------------
def embed_texts(texts: List[str]) -> np.ndarray:
    vecs = []
    for t in texts:
        r = embedding(model=EMB_MODEL, input=t)
        vecs.append(r["data"][0]["embedding"])
    X = np.array(vecs, dtype="float32")
    faiss.normalize_L2(X)  # cosine via inner product
    return X

# ---------------- Store ----------------
class FaissStore:
    """
    Index: IndexFlatIP (cosine via L2-normalized vectors)
    Files:
      - {dir}/faiss.index
      - {dir}/chunks.jsonl
      - {dir}/ids.json
    """
    def __init__(self, dirpath: Optional[str] = None):
        self.dir = dirpath or PROCESSED_DIR
        os.makedirs(self.dir, exist_ok=True)
        self.index_path = os.path.join(self.dir, "faiss.index")
        self.meta_path  = os.path.join(self.dir, "chunks.jsonl")
        self.ids_path   = os.path.join(self.dir, "ids.json")

    # ---- meta/ids IO
    def _load_meta(self) -> List[Dict]:
        if not os.path.exists(self.meta_path): return []
        return [json.loads(l) for l in open(self.meta_path, "r", encoding="utf-8")]

    def _save_meta(self, items: List[Dict]) -> None:
        with open(self.meta_path, "w", encoding="utf-8") as f:
            for it in items:
                f.write(json.dumps(it, ensure_ascii=False) + "\n")

    def _load_ids(self) -> List[str]:
        if not os.path.exists(self.ids_path): return []
        return json.load(open(self.ids_path, "r", encoding="utf-8"))

    def _save_ids(self, ids: List[str]) -> None:
        json.dump(ids, open(self.ids_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    # ---- index IO
    def _read_index(self) -> Optional[faiss.Index]:
        if not os.path.exists(self.index_path): return None
        return faiss.read_index(self.index_path)

    def _write_index(self, index: faiss.Index) -> None:
        faiss.write_index(index, self.index_path)

    # ---- build
    def _build_index_from_meta(self, meta: List[Dict]) -> Tuple[faiss.Index, List[str]]:
        texts = [c.get("text", "") for c in meta]
        X = embed_texts(texts)
        index = faiss.IndexFlatIP(X.shape[1])
        index.add(X)
        ids_order = [c["id"] for c in meta]
        return index, ids_order

    # ---- upsert
    def upsert(self, chunks: List[Dict]) -> Tuple[int, int]:
        # merge meta
        old_meta_by_id = {c["id"]: c for c in self._load_meta()}
        for c in chunks:
            old_meta_by_id[c["id"]] = c
        merged = list(old_meta_by_id.values())
        self._save_meta(merged)

        index = self._read_index()
        ids_order = self._load_ids()

        if index is None:
            index, ids_order = self._build_index_from_meta(merged)
            self._write_index(index); self._save_ids(ids_order)
            return index.ntotal, len(ids_order)

        known = set(ids_order)
        new_items = [c for c in merged if c["id"] not in known]
        if not new_items:
            self._write_index(index); self._save_ids(ids_order)
            return index.ntotal, 0

        Xnew = embed_texts([c["text"] for c in new_items])
        if Xnew.shape[1] != index.d:
            index, ids_order = self._build_index_from_meta(merged)
            self._write_index(index); self._save_ids(ids_order)
            return index.ntotal, len(merged) - len(known)

        index.add(Xnew)
        ids_order.extend([c["id"] for c in new_items])
        self._write_index(index); self._save_ids(ids_order)
        return index.ntotal, len(new_items)

    # ---- search (표준 반환 스키마)
    def search(self, query: str, k: int = 6) -> List[Dict]:
        index = self._read_index()
        if index is None or index.ntotal == 0:
            return []
        Q = embed_texts([query])
        D, I = index.search(Q, min(k, index.ntotal))
        idxs, scores = I[0].tolist(), D[0].tolist()

        meta_list = self._load_meta()
        ids_order = self._load_ids()
        meta_by_id = {c["id"]: c for c in meta_list}

        out: List[Dict] = []
        for ii, sc in zip(idxs, scores):
            if ii < 0 or ii >= len(ids_order):
                continue
            cid = ids_order[ii]
            m = meta_by_id.get(cid, {"id": cid})
            out.append({
                "id": cid,
                "title": m.get("title", ""),
                "url": m.get("source", ""),        # 표준 필드 제공
                "source": m.get("source", ""),
                "summary": (m.get("text", "")[:300]),
                "text": m.get("text", ""),
                "page": m.get("page", 1),
                "kind": m.get("kind", ""),
                "score": float(sc),
            })
        return out

    # ---- aliases
    def query(self, query: str, k: int = 6) -> List[Dict]:
        return self.search(query, k=k)
    def similarity_search(self, query: str, k: int = 6) -> List[Dict]:
        return self.search(query, k=k)
    def search_top_k(self, query: str, k: int = 6) -> List[Dict]:
        return self.search(query, k=k)
