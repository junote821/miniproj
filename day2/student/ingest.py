import os, glob, hashlib
from typing import List, Dict
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(), override=False)

from day2.student.rag_store import FaissStore

RAW_DIR = os.getenv("RAG_RAW_DIR", "data/raw")
INDEX_DIR = os.getenv("D2_INDEX_DIR", "data/processed/day2/faiss")

def _file_id(path: str) -> str:
    h = hashlib.md5(); h.update(path.encode("utf-8")); return h.hexdigest()

def collect_sources_from_folder(raw_dir: str = RAW_DIR,
                                allowed_exts = (".txt",".md"),
                                recursive: bool = True) -> List[str]:
    """
    TODO-D2-7: raw_dir에서 허용 확장자 파일을 모두 찾기
    - recursive=True면 하위 폴더까지
    - 중복 제거 후 파일 경로 리스트 반환
    """
    pattern = "**/*" if recursive else "*"
    files = [p for p in glob.glob(os.path.join(raw_dir, pattern), recursive=recursive)
             if os.path.splitext(p)[1].lower() in allowed_exts]
    return sorted(list(set(files)))

def read_text_auto(src: str) -> Dict:
    """
    TODO-D2-8: 파일 경로(src)에서 텍스트 읽어서 dict 반환
    - {"text": str, "meta": {"source": src, "title": basename, "type":"file"}}
    - (선택) URL 처리: requests+BS4
    """
    try:
        with open(src, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception:
        text = ""
    return {"text": text, "meta": {"source": src, "title": os.path.basename(src), "type": "file"}}

def chunk_text(text: str, chunk_size: int = 800, overlap: int = 200) -> List[str]:
    """
    TODO-D2-9: 공백 정규화 후 슬라이딩 윈도우로 청크 분할
    - 빈 청크 제거
    """
    s = " ".join((text or "").split())
    if not s: return []
    chunks = []
    i = 0
    while i < len(s):
        chunks.append(s[i:i+chunk_size])
        i += max(1, chunk_size - overlap)
    return [c for c in chunks if c.strip()]

def ingest_sources(sources: List[str], out_dir: str = INDEX_DIR) -> List[Dict]:
    """
    TODO-D2-10: 각 파일을 읽어 청크 리스트 생성
    - 청크 스키마:
      {
        "id": md5(f"{source}::{i}"),
        "text": <chunk>,
        "source": <path or url>,
        "page": i+1,
        "kind": "local",
        "title": <파일명 or 도메인>
      }
    - 반환: 모든 청크 리스트
    """
    import hashlib
    chunks: List[Dict] = []
    for src in sources:
        obj = read_text_auto(src)
        text, meta = obj["text"], obj["meta"]
        for i, ck in enumerate(chunk_text(text)):
            cid = hashlib.md5(f"{meta['source']}::{i}".encode("utf-8")).hexdigest()
            chunks.append({
                "id": cid,
                "text": ck,
                "source": meta["source"],
                "page": i+1,
                "kind": "local",
                "title": meta["title"]
            })
    return chunks

def main():
    os.makedirs(INDEX_DIR, exist_ok=True)
    files = collect_sources_from_folder(RAW_DIR)
    print(f"[INGEST] found files: {len(files)}")
    chunks = ingest_sources(files, INDEX_DIR)
    store = FaissStore.load_or_new(index_dir=INDEX_DIR)
    ntotal, n_added = store.upsert(chunks)
    print(f"[INGEST] total={ntotal}, added={n_added}")
    print(f"[INGEST] index_dir={INDEX_DIR}")

if __name__ == "__main__":
    main()
