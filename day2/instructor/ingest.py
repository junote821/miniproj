import os, re, json, hashlib, requests
from pathlib import Path
from typing import List, Dict
from bs4 import BeautifulSoup
from pypdf import PdfReader

# --- ENV 옵션 ---
USER_AGENT = os.getenv("RAG_USER_AGENT", "Mozilla/5.0 (Day2-Ingest-Instructor)")
REQUEST_TIMEOUT = int(os.getenv("RAG_REQUEST_TIMEOUT", "15"))
RAW_DIR = os.getenv("RAG_RAW_DIR", "data/raw")
PROCESSED_DIR = os.getenv("RAG_PROCESSED_DIR", "data/processed/day2")
URL_SNAPSHOT = os.getenv("RAG_URL_SNAPSHOT", "0") == "1"

def _md5(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()

def read_text_from_pdf(path: str) -> str:
    text = []
    with open(path, "rb") as f:
        pdf = PdfReader(f)
        for page in pdf.pages:
            try:
                text.append(page.extract_text() or "")
            except Exception:
                text.append("")
    return "\n".join(text)

def read_text_from_url(url: str, timeout: int = REQUEST_TIMEOUT) -> str:
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text)
    return text

def read_text_auto(src: str) -> Dict:
    """src: 로컬(.pdf/.txt/.md) 또는 http(s) URL -> {'text','meta'}"""
    if src.startswith(("http://", "https://")):
        txt = read_text_from_url(src)
        meta = {"source": src, "type": "url", "title": src}
        # URL 스냅샷 보관(옵션)
        if URL_SNAPSHOT:
            out_dir = Path(RAW_DIR) / "url_snapshots"
            out_dir.mkdir(parents=True, exist_ok=True)
            safe = _md5(src) + ".txt"
            (out_dir / safe).write_text(txt, encoding="utf-8", errors="ignore")
    else:
        p = Path(src)
        if not p.exists():
            raise FileNotFoundError(src)
        if p.suffix.lower() == ".pdf":
            txt = read_text_from_pdf(str(p))
        else:
            txt = p.read_text(encoding="utf-8", errors="ignore")
        meta = {"source": str(p), "type": p.suffix.lower().lstrip(".") or "file", "title": p.name}
    return {"text": txt, "meta": meta}

def chunk_text(text: str, chunk_size: int = 800, overlap: int = 200) -> List[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    chunks = []
    start, n = 0, len(text)
    while start < n:
        end = min(start + chunk_size, n)
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk)
        if end == n:
            break
        start = max(0, end - overlap)
    return chunks

def ingest_sources(sources: List[str], out_dir: str | None = None) -> List[Dict]:
    """
    반환: [{id,text,source,page,kind,title}]
    - id = md5(source+page)
    - 빈/중복 청크 제외
    """
    out_dir = out_dir or PROCESSED_DIR
    os.makedirs(out_dir, exist_ok=True)

    seen_ids = set()
    all_chunks: List[Dict] = []
    for src in sources:
        data = read_text_auto(src)
        chunks = chunk_text(data["text"])
        for i, c in enumerate(chunks):
            cid = _md5(f"{data['meta']['source']}::{i}")
            if cid in seen_ids or not c.strip():
                continue
            seen_ids.add(cid)
            all_chunks.append({
                "id": cid,
                "text": c,
                "source": data["meta"]["source"],
                "page": i + 1,
                "kind": data["meta"]["type"],
                "title": data["meta"].get("title") or data["meta"]["source"],
            })

    # 저장(덮어쓰기: 재현성)
    with open(os.path.join(out_dir, "chunks.jsonl"), "w", encoding="utf-8") as f:
        for ch in all_chunks:
            f.write(json.dumps(ch, ensure_ascii=False) + "\n")
    return all_chunks
