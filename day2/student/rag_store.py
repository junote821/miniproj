import os
import json
import faiss
import numpy as np
from typing import List, Dict, Tuple, Optional
from litellm import embedding

# ===== 설정 =====
EMB_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
DEFAULT_INDEX_DIR = os.getenv("D2_INDEX_DIR", "data/processed/day2/faiss")
BATCH = int(os.getenv("EMBED_BATCH", "8"))

# ===== 임베딩 =====
def embed_texts(texts: List[str]) -> np.ndarray:
    """
    TODO-D2-1: 문자열 리스트 -> L2 정규화된 float32 벡터(np.ndarray) 생성
    - litellm.embedding(model=EMB_MODEL, input=...) 호출
    - 배치(BATCH) 처리 → 실패 시 개별 처리 폴백
    - faiss.normalize_L2(X) 적용 (코사인 유사도용)
    - 빈 입력이면 shape=(0, D)의 안전한 배열 반환
    """
    # --- 구현 힌트(주석): vecs 리스트 -> np.array -> normalize ---
    # raise NotImplementedError("TODO-D2-1: embed_texts를 구현하세요.")
    vecs: List[List[float]] = []
    if not texts:
        return np.zeros((0, 1536), dtype="float32")
    if BATCH > 1 and len(texts) > 1:
        for i in range(0, len(texts), BATCH):
            chunk = texts[i:i+BATCH]
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
    faiss.normalize_L2(X)
    return X

# ===== FAISS Store =====
class FaissStore:
    """
    간단 로컬 FAISS 스토어 (코사인 유사도: IndexFlatIP + L2 정규화)
    파일:
      {dir}/faiss.index
      {dir}/chunks.jsonl
      {dir}/ids.json
    공개 메서드:
      - upsert(chunks) -> (ntotal, n_added)
      - search(query, k) -> 표준 스키마 리스트
      - ntotal() -> int
    호환 별칭:
      - query(), similarity_search(), search_top_k()
    클래스 메서드:
      - load_or_new(index_dir), load(index_dir)
    """
    def __init__(self, index_dir: Optional[str] = None):
        """
        TODO-D2-2: 인덱스 디렉토리/파일 경로 설정 및 디렉토리 생성
        - self.dir, self.index_path, self.meta_path, self.ids_path
        """
        self.dir = index_dir or DEFAULT_INDEX_DIR
        os.makedirs(self.dir, exist_ok=True)
        self.index_path = os.path.join(self.dir, "faiss.index")
        self.meta_path  = os.path.join(self.dir, "chunks.jsonl")
        self.ids_path   = os.path.join(self.dir, "ids.json")

    # ----- 클래스 메서드 -----
    @classmethod
    def load_or_new(cls, index_dir: Optional[str] = None) -> "FaissStore":
        """
        TODO-D2-3: Day4 호환 목적. 존재 여부와 상관없이 핸들만 반환해도 OK.
        """
        return cls(index_dir=index_dir)

    @classmethod
    def load(cls, index_dir: Optional[str] = None) -> "FaissStore":
        # 단순화: load_or_new와 동일 동작 허용
        return cls(index_dir=index_dir)

    # ----- 내부 IO: meta/ids -----
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

    # ----- 내부 IO: index -----
    def _read_index(self) -> Optional[faiss.Index]:
        if not os.path.exists(self.index_path): return None
        return faiss.read_index(self.index_path)

    def _write_index(self, index: faiss.Index) -> None:
        faiss.write_index(index, self.index_path)

    # ----- 인덱스 생성 -----
    def _build_index_from_meta(self, meta: List[Dict]) -> Tuple[faiss.Index, List[str]]:
        """
        TODO-D2-4:
        - meta의 'text'로 임베딩 → IndexFlatIP(d) 생성 → index.add(X)
        - ids_order = [c["id"] for c in meta]
        - (index, ids_order) 반환
        """
        texts = [c.get("text", "") for c in meta]
        X = embed_texts(texts)
        index = faiss.IndexFlatIP(X.shape[1]) if X.size else faiss.IndexFlatIP(1536)
        if X.size:
            index.add(X)
        ids_order = [c["id"] for c in meta]
        return index, ids_order

    # ----- upsert -----
    def upsert(self, chunks: List[Dict]) -> Tuple[int, int]:
        """
        TODO-D2-5:
        - 기존 meta 병합(ID 기준) → 저장
        - 인덱스가 없으면 전체 빌드
        - 있으면 신규 ID만 임베딩 후 add
        - 차원 불일치면 전체 재빌드
        - (ntotal, n_added) 반환
        """
        old_by_id = {c["id"]: c for c in self._load_meta()}
        for c in chunks or []:
            old_by_id[c["id"]] = c
        merged = list(old_by_id.values())
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
        # 차원 불일치 → 전체 재빌드
        if Xnew.size and Xnew.shape[1] != index.d:
            index, ids_order = self._build_index_from_meta(merged)
            self._write_index(index); self._save_ids(ids_order)
            return index.ntotal, len(merged) - len(known)

        if Xnew.size:
            index.add(Xnew)
            ids_order.extend([c["id"] for c in new_items])

        self._write_index(index); self._save_ids(ids_order)
        return index.ntotal, len(new_items)

    # ----- search -----
    def search(self, query: str, k: int = 6) -> List[Dict]:
        """
        TODO-D2-6: 질의 임베딩 → index.search → 표준 스키마로 반환
        표준 스키마:
        {
          "id","title","url","source",
          "summary","text","page","kind","score"
        }
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
            cid = ids_order[ii]
            m = meta_by_id.get(cid, {"id": cid})
            out.append({
                "id": cid,
                "title": m.get("title", ""),
                "url": m.get("source", ""),
                "source": m.get("source", ""),
                "summary": (m.get("text", "")[:300]),
                "text": m.get("text", ""),
                "page": m.get("page", 1),
                "kind": m.get("kind", ""),
                "score": float(sc),
            })
        return out

    # ----- info & aliases -----
    def ntotal(self) -> int:
        idx = self._read_index()
        return int(idx.ntotal) if idx is not None else 0

    def query(self, query: str, k: int = 6) -> List[Dict]:
        return self.search(query, k=k)
    def similarity_search(self, query: str, k: int = 6) -> List[Dict]:
        return self.search(query, k=k)
    def search_top_k(self, query: str, k: int = 6) -> List[Dict]:
        return self.search(query, k=k)
