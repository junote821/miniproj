import os
import json
import faiss
import numpy as np
from typing import List, Dict, Tuple, Optional
from litellm import embedding

# ---------------- Config ----------------
EMB_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
DEFAULT_INDEX_DIR = os.getenv("D2_INDEX_DIR", "data/processed/day2/faiss")
BATCH = int(os.getenv("EMBED_BATCH", "8"))
MIN_SCORE = float(os.getenv("RAG_MIN_SCORE", "0.0"))  # 하위 유사도 컷오프 (0~1 내적값)

# ---------------- Embedding ----------------
def embed_texts(texts: List[str]) -> np.ndarray:
    """문자열 리스트 -> L2 정규화된 float32 벡터(np.ndarray)"""
    if not texts:
        return np.zeros((0, 1536), dtype="float32")
    vecs: List[List[float]] = []
    if BATCH > 1 and len(texts) > 1:
        for i in range(0, len(texts), BATCH):
            chunk = texts[i : i + BATCH]
            try:
                r = embedding(model=EMB_MODEL, input=chunk)
                for obj in r["data"]:
                    vecs.append(obj["embedding"])
            except Exception:
                for t in chunk:
                    rr = embedding(model=EMB_MODEL, input=t)
                    vecs.append(rr["data"][0]["embedding"])
    else:
        for t in texts:
            r = embedding(model=EMB_MODEL, input=t)
            vecs.append(r["data"][0]["embedding"])

    X = np.array(vecs, dtype="float32")
    faiss.normalize_L2(X)  # cosine via inner product
    return X

# ---------------- Store ----------------
class FaissStore:
    """
    아주 단순한 로컬 FAISS 스토어.
    파일:
      {index_dir}/faiss.index
      {index_dir}/chunks.jsonl   # 메타 rows
      {index_dir}/ids.json       # 벡터 순서에 대응하는 id 리스트
    공개 메서드:
      upsert(chunks) -> (ntotal, n_added)
      search(query, k) -> [{...}]
      ntotal() -> int
      reset_index() -> None
      rebuild() -> int            # 메타 전체로 재빌드
    """

    # ---------- 생성/경로 ----------
    def __init__(self, index_dir: Optional[str] = None):
        self.dir = index_dir or DEFAULT_INDEX_DIR
        os.makedirs(self.dir, exist_ok=True)
        self.index_path = os.path.join(self.dir, "faiss.index")
        self.meta_path  = os.path.join(self.dir, "chunks.jsonl")
        self.ids_path   = os.path.join(self.dir, "ids.json")

    @classmethod
    def load_or_new(cls, index_dir: Optional[str] = None) -> "FaissStore":
        return cls(index_dir=index_dir)

    @classmethod
    def load(cls, index_dir: Optional[str] = None) -> "FaissStore":
        return cls(index_dir=index_dir)

    # ---------- 내부 IO ----------
    def _load_meta(self) -> List[Dict]:
        if not os.path.exists(self.meta_path): return []
        with open(self.meta_path, "r", encoding="utf-8") as f:
            return [json.loads(l) for l in f]

    def _save_meta(self, items: List[Dict]) -> None:
        with open(self.meta_path, "w", encoding="utf-8") as f:
            for it in items:
                f.write(json.dumps(it, ensure_ascii=False) + "\n")

    def _load_ids(self) -> List[str]:
        if not os.path.exists(self.ids_path): return []
        with open(self.ids_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_ids(self, ids: List[str]) -> None:
        with open(self.ids_path, "w", encoding="utf-8") as f:
            json.dump(ids, f, ensure_ascii=False, indent=2)

    def _read_index(self) -> Optional[faiss.Index]:
        if not os.path.exists(self.index_path): return None
        return faiss.read_index(self.index_path)

    def _write_index(self, index: faiss.Index) -> None:
        faiss.write_index(index, self.index_path)

    # ---------- 빌드/리셋 ----------
    def _build_index_from_meta(self, meta: List[Dict]) -> Tuple[faiss.Index, List[str]]:
        texts = [c.get("text", "") for c in meta]
        if not texts:
            dim = 1536  # 기본 차원(placeholder)
            return faiss.IndexFlatIP(dim), []
        X = embed_texts(texts)
        index = faiss.IndexFlatIP(X.shape[1])
        index.add(X)
        ids_order = [c["id"] for c in meta]
        return index, ids_order

    def reset_index(self) -> None:
        """faiss.index/ids.json만 삭제 (메타는 보존)."""
        if os.path.exists(self.index_path): os.remove(self.index_path)
        if os.path.exists(self.ids_path): os.remove(self.ids_path)

    def rebuild(self) -> int:
        """메타(chunks.jsonl) 전체로 인덱스 재생성. 반환: ntotal"""
        meta = self._load_meta()
        index, ids_order = self._build_index_from_meta(meta)
        self._write_index(index); self._save_ids(ids_order)
        return index.ntotal

    # ---------- upsert ----------
    def upsert(self, chunks: List[Dict]) -> Tuple[int, int]:
        if not chunks:
            index = self._read_index()
            return (index.ntotal if index is not None else 0, 0)

        # 1) 메타 병합
        old_meta_by_id = {c["id"]: c for c in self._load_meta()}
        for c in chunks:
            old_meta_by_id[c["id"]] = c
        merged = list(old_meta_by_id.values())
        self._save_meta(merged)

        index = self._read_index()
        ids_order = self._load_ids()

        # 2) 처음 생성
        if index is None:
            index, ids_order = self._build_index_from_meta(merged)
            self._write_index(index); self._save_ids(ids_order)
            return index.ntotal, len(ids_order)

        # 3) 신규만 추가
        known = set(ids_order)
        new_items = [c for c in merged if c["id"] not in known]
        if not new_items:
            self._write_index(index); self._save_ids(ids_order)
            return index.ntotal, 0

        Xnew = embed_texts([c["text"] for c in new_items])

        # 4) 차원 불일치 → 전체 재빌드
        if Xnew.shape[1] != index.d:
            index, ids_order = self._build_index_from_meta(merged)
            self._write_index(index); self._save_ids(ids_order)
            return index.ntotal, len(merged) - len(known)

        # 5) 증분 추가
        index.add(Xnew)
        ids_order.extend([c["id"] for c in new_items])
        self._write_index(index); self._save_ids(ids_order)
        return index.ntotal, len(new_items)

    # ---------- search ----------
    def search(self, query: str, k: int = 6) -> List[Dict]:
        """
        표준 반환 스키마:
        [{id,title,url,source,summary,text,page,kind,score}, ...]
        """
        index = self._read_index()
        if index is None or index.ntotal == 0:
            return []

        Q = embed_texts([query])
        kk = min(max(1, k), index.ntotal)
        D, I = index.search(Q, kk)
        idxs, scores = I[0].tolist(), D[0].tolist()

        meta_list = self._load_meta()
        ids_order = self._load_ids()
        meta_by_id = {c["id"]: c for c in meta_list}

        out: List[Dict] = []
        for ii, sc in zip(idxs, scores):
            if ii < 0 or ii >= len(ids_order):
                continue
            if sc < MIN_SCORE:
                continue
            cid = ids_order[ii]
            m = meta_by_id.get(cid, {"id": cid})
            title = (m.get("title", "") or "")[:140]
            text = m.get("text", "") or ""
            out.append({
                "id": cid,
                "title": title,
                "url": m.get("source", ""),
                "source": m.get("source", ""),
                "summary": text[:300],
                "text": text,
                "page": m.get("page", 1),
                "kind": m.get("kind", ""),
                "score": float(sc),
            })
        return out

    # ---------- info & aliases ----------
    def ntotal(self) -> int:
        idx = self._read_index()
        return int(idx.ntotal) if idx is not None else 0

    def query(self, query: str, k: int = 6) -> List[Dict]:
        return self.search(query, k=k)

    def similarity_search(self, query: str, k: int = 6) -> List[Dict]:
        return self.search(query, k=k)

    def search_top_k(self, query: str, k: int = 6) -> List[Dict]:
        return self.search(query, k=k)
