import os, re, glob, hashlib, requests
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
    # 가장 간단한 방식: 유니코드 추출 시도 (PyPDF2 등 없을 때)
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

def read_url_text(url: str) -> str:
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    html = r.text
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    return text

def read_text_auto(path_or_url: str) -> Tuple[str, str]:
    # 반환: (title, text)
    if re.match(r"^https?://", path_or_url):
        text = read_url_text(path_or_url)
        return (path_or_url, text)
    lower = path_or_url.lower()
    if lower.endswith(".pdf"):
        return (os.path.basename(path_or_url), read_pdf_file(path_or_url))
    if lower.endswith(".md"):
        return (os.path.basename(path_or_url), read_md_file(path_or_url))
    if lower.endswith(".txt"):
        return (os.path.basename(path_or_url), read_text_file(path_or_url))
    # 기본 텍스트 시도
    try:
        return (os.path.basename(path_or_url), read_text_file(path_or_url))
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
    # txt/md/pdf
    for pat in ("*.txt", "*.md", "*.pdf"):
        paths += glob.glob(os.path.join(folder, pat))
    # urls.txt 자동 로드
    url_list = os.path.join(folder, "urls.txt")
    if os.path.exists(url_list):
        for line in open(url_list, "r", encoding="utf-8"):
            u = line.strip()
            if not u:
                continue
            paths.append(u)
    return paths

def ingest_sources(paths: Optional[List[str]] = None,
                   chunk_size: int = 800, overlap: int = 100,
                   kind: str = "generic") -> List[Dict]:
    paths = paths or collect_sources_from_folder(RAW_DIR)
    out: List[Dict] = []
    for p in paths:
        title, text = read_text_auto(p)
        if not text:
            continue
        chunks = chunk_text(text, chunk_size=chunk_size, overlap=overlap)
        base = title or os.path.basename(p)
        for j, t in enumerate(chunks, 1):
            cid = hashlib.md5((base + str(j)).encode("utf-8")).hexdigest()
            out.append({
                "id": cid,
                "text": t,
                "source": p,        # URL or File path
                "page": j,
                "kind": kind,
                "title": base,
            })
    return out
