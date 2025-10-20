import os, json, faiss, numpy as np
from typing import List, Dict, Tuple
from litellm import embedding

EMB_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
PROCESSED_DIR = os.getenv("RAG_PROCESSED_DIR", "data/processed/day2")

def embed_texts(texts: List[str]) -> np.ndarray:
    vecs = []
    for t in texts:
        resp = embedding(model=EMB_MODEL, input=t)
        vecs.append(resp["data"][0]["embedding"])
    return np.array(vecs, dtype="float32")

class FaissStore:
    def __init__(self, dirpath: str | None = None):
        self.dir = dirpath or os.getenv("RAG_PROCESSED_DIR", "data/processed/day2")
        os.makedirs(self.dir, exist_ok=True)
        self.index_path = os.path.join(self.dir, "faiss.index")
        self.meta_path  = os.path.join(self.dir, "chunks.jsonl")
        self.ids_path   = os.path.join(self.dir, "ids.json")

    def _load_meta(self):
        if not os.path.exists(self.meta_path): return []
        return [json.loads(l) for l in open(self.meta_path, "r", encoding="utf-8")]

    def _save_meta(self, items): 
        with open(self.meta_path, "w", encoding="utf-8") as f:
            for it in items: f.write(json.dumps(it, ensure_ascii=False) + "\n")

    def _load_ids(self):
        if not os.path.exists(self.ids_path): return []
        return json.load(open(self.ids_path, "r", encoding="utf-8"))

    def _save_ids(self, ids):
        json.dump(ids, open(self.ids_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    def upsert(self, chunks: List[Dict]):
        # 1) 메타 병합(중복 id 제거)
        old = {c["id"]: c for c in self._load_meta()}
        for c in chunks: old[c["id"]] = c
        merged = list(old.values()); self._save_meta(merged)

        # 2) 증분 대상 계산
        known_ids = set(self._load_ids())
        new_items = [c for c in merged if c["id"] not in known_ids]
        if not new_items and os.path.exists(self.index_path):
            index = faiss.read_index(self.index_path)
            return index.ntotal, 0

        # 3) 인덱스 로드/생성
        if os.path.exists(self.index_path):
            index = faiss.read_index(self.index_path)
            dim = index.d
        else:
            # 첫 빌드: 전체 임베딩
            X = embed_texts([c["text"] for c in merged])
            dim = X.shape[1]; index = faiss.IndexFlatIP(dim)
            faiss.normalize_L2(X); index.add(X)
            faiss.write_index(index, self.index_path)
            self._save_ids([c["id"] for c in merged])
            return index.ntotal, len(merged)

        # 4) 새 항목만 임베딩 후 append
        if new_items:
            Xnew = embed_texts([c["text"] for c in new_items])
            if Xnew.shape[1] != dim:
                # 차원 바뀌었으면 안전하게 전체 재빌드
                Xall = embed_texts([c["text"] for c in merged])
                index = faiss.IndexFlatIP(Xall.shape[1])
                faiss.normalize_L2(Xall); index.add(Xall)
                self._save_ids([c["id"] for c in merged])
            else:
                faiss.normalize_L2(Xnew); index.add(Xnew)
                self._save_ids(list(known_ids | {c["id"] for c in new_items}))

        faiss.write_index(index, self.index_path)
        return index.ntotal, len(new_items)
