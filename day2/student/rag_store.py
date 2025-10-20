# Day2 학생용 스캐폴딩 — rag_store.py
# 목적: 텍스트 임베딩 → FAISS 인덱스 업서트/검색
# 강사용과 동일 시그니처/리턴 포맷 유지.

import os, json, faiss, numpy as np
from typing import List, Dict, Tuple
from litellm import embedding  # OpenAI 등 통합
EMB_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
PROCESSED_DIR = os.getenv("RAG_PROCESSED_DIR", "data/processed/day2")

# --- TODO[Step B2-1]: 임베딩 함수 ---
def embed_texts(texts: List[str]) -> np.ndarray:
    """
    요구사항:
    - litellm.embedding(model=EMB_MODEL, input=<text>) 호출
    - resp['data'][0]['embedding'] → float list
    - np.array(dtype=float32)로 반환, shape=(N, D)
    """
    vecs = []
    for t in texts:
        resp = embedding(model=EMB_MODEL, input=t)
        vecs.append(resp["data"][0]["embedding"])
    return np.array(vecs, dtype="float32")

class FaissStore:
    def __init__(self, dirpath: str | None = None):
        self.dir = dirpath or PROCESSED_DIR
        os.makedirs(self.dir, exist_ok=True)
        self.index_path = os.path.join(self.dir, "faiss.index")
        self.meta_path  = os.path.join(self.dir, "chunks.jsonl")
        # (선택 과제) 증분 모드용 id 목록
        self.ids_path   = os.path.join(self.dir, "ids.json")

    def _load_meta(self) -> List[Dict]:
        if not os.path.exists(self.meta_path): return []
        return [json.loads(l) for l in open(self.meta_path, "r", encoding="utf-8")]

    def _save_meta(self, items: List[Dict]) -> None:
        with open(self.meta_path, "w", encoding="utf-8") as f:
            for it in items:
                f.write(json.dumps(it, ensure_ascii=False) + "\n")

    # --- TODO[Step B2-2]: 업서트(재빌드 or 증분) ---
    def upsert(self, chunks: List[Dict]) -> Tuple[int, int]:
        """
        요구사항(둘 중 택1):
        A) 간단 재빌드:
           - 기존 메타 + 신규 chunks 병합(중복 id 제거) → 전체 임베딩 → 새 IndexFlatIP(d) 생성 → add → 저장
        B) 증분:
           - ids.json 로드 → unseen id만 임베딩해 기존 인덱스에 add
           - 차원 불일치 시 안전하게 전체 재빌드
        반환: (index.ntotal, 이번에 추가한 개수)
        """
        # 기본: 간단 재빌드 구현 (권장)
        old = {c["id"]: c for c in self._load_meta()}
        for c in chunks:
            old[c["id"]] = c
        merged = list(old.values())
        self._save_meta(merged)

        if not merged:
            if os.path.exists(self.index_path):
                os.remove(self.index_path)
            return 0, 0

        X = embed_texts([c["text"] for c in merged])
        dim = X.shape[1]
        index = faiss.IndexFlatIP(dim)
        faiss.normalize_L2(X)
        index.add(X)
        faiss.write_index(index, self.index_path)
        return index.ntotal, len(chunks)

    # --- TODO[Step B3-1]: 검색 ---
    def search(self, query: str, k: int = 5) -> List[Dict]:
        """
        요구사항:
        - faiss.index 로드
        - query 임베딩 → normalize → index.search(qv, k)
        - 메타(chunks.jsonl)에서 해당 행을 찾아 score와 함께 반환
        """
        if not (os.path.exists(self.index_path) and os.path.exists(self.meta_path)):
            return []
        index = faiss.read_index(self.index_path)
        qv = embed_texts([query])
        faiss.normalize_L2(qv)
        D, I = index.search(qv, k)

        metas = self._load_meta()
        out = []
        for idx, score in zip(I[0], D[0]):
            if idx < 0 or idx >= len(metas):
                continue
            m = dict(metas[idx])
            m["score"] = float(score)
            out.append(m)
        return out
