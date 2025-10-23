import os, re, glob, hashlib, requests, json
from typing import List, Dict, Tuple, Optional
from dotenv import load_dotenv, find_dotenv
from bs4 import BeautifulSoup

load_dotenv(find_dotenv(), override=False)

REQUEST_TIMEOUT = int(os.getenv("RAG_REQUEST_TIMEOUT", "15"))
USER_AGENT = os.getenv("RAG_USER_AGENT", "Mozilla/5.0 (Day2-Instructor)")
RAW_DIR = os.getenv("RAG_RAW_DIR", "data/raw")

def read_text_file(path: str) -> str:
    return open(path, "r", encoding="utf-8").read()

def read_md_file(path: str) -> str:
    return read_text_file(path)

def read_pdf_file(path: str) -> str:
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(path)
        texts = []
        for page in reader.pages:
            try:
                texts.append(page.extract_text() or "")
            except Exception:
                pass
        return "\n".join(texts)
    except Exception:
        return ""

def read_url_text(url: str) -> Tuple[str, str]:
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    html = r.text
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    title = (soup.title.string.strip() if soup.title and soup.title.string else url)
    # H1이 있으면 보조 타이틀
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        title = h1.get_text(strip=True)
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    return (title, text)

def read_text_auto(path_or_url: str) -> Tuple[str, str]:
    # 반환: (title, text)
    if re.match(r"^https?://", path_or_url):
        return read_url_text(path_or_url)

    lower = path_or_url.lower()
    if lower.endswith(".pdf"):
        return (os.path.basename(path_or_url), read_pdf_file(path_or_url))
    if lower.endswith(".md"):
        # 첫 헤더를 타이틀로
        txt = read_md_file(path_or_url)
        m = re.search(r"^\s*#\s+(.+)$", txt, flags=re.M)
        title = m.group(1).strip() if m else os.path.basename(path_or_url)
        return (title, txt)
    if lower.endswith(".txt"):
        txt = read_text_file(path_or_url)
        first = (txt.strip().splitlines() or [""])[0].strip()
        title = first[:80] or os.path.basename(path_or_url)
        return (title, txt)

    try:
        txt = read_text_file(path_or_url)
        first = (txt.strip().splitlines() or [""])[0].strip()
        title = first[:80] or os.path.basename(path_or_url)
        return (title, txt)
    except Exception:
        return (os.path.basename(path_or_url), "")

def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> List[str]:
    chunks = []
    i = 0
    n = len(text)
    step = max(1, chunk_size - overlap)
    while i < n:
        chunks.append(text[i:i+chunk_size])
        i += step
    return chunks

def collect_sources_from_folder(folder: str = RAW_DIR) -> List[str]:
    paths = []
    for pat in ("*.txt", "*.md", "*.pdf"):
        paths += glob.glob(os.path.join(folder, pat))
    url_list = os.path.join(folder, "urls.txt")
    if os.path.exists(url_list):
        for line in open(url_list, "r", encoding="utf-8"):
            u = line.strip()
            if u:
                paths.append(u)
    return paths

def ingest_sources(paths: Optional[List[str]] = None,
                   chunk_size: int = 800,
                   overlap: int = 100,
                   kind: str = "generic",
                   out_dir: str = "data/processed/day2/faiss",
                   save_chunks: bool = True) -> List[Dict]:
    """
    paths: 파일/URL 리스트(없으면 RAW_DIR에서 수집)
    반환: [{"id","text","source","page","kind","title"}, ...]
    - save_chunks=True이면 out_dir/chunks.jsonl 로 라인 단위 JSON 저장
    """
    paths = paths or collect_sources_from_folder(RAW_DIR)
    out: List[Dict] = []

    for p in paths:
        title, text = read_text_auto(p)
        if not text:
            continue
        chunks = chunk_text(text, chunk_size=chunk_size, overlap=overlap)
        base = title or os.path.basename(p)
        for j, t in enumerate(chunks, 1):
            cid = hashlib.md5((base + "::" + str(j)).encode("utf-8")).hexdigest()
            out.append({
                "id": cid,
                "text": t,
                "source": p,        # URL or File path
                "page": j,
                "kind": kind,
                "title": base,
            })

    if save_chunks:
        os.makedirs(out_dir, exist_ok=True)
        jpath = os.path.join(out_dir, "chunks.jsonl")
        with open(jpath, "w", encoding="utf-8") as f:
            for row in out:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"[Ingest] wrote {len(out)} chunks → {jpath}")

    return out
