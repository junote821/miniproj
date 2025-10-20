# Day2 스캐폴딩
# 목적: 폴더/URL의 문서를 읽어 텍스트화 → 청크로 쪼개고 메타데이터를 붙여 반환

import os, re, json, hashlib, requests
from pathlib import Path
from typing import List, Dict
from bs4 import BeautifulSoup
from pypdf import PdfReader

# ENV 키 (변경하지 말 것)
USER_AGENT = os.getenv("RAG_USER_AGENT", "Mozilla/5.0 (Day2-Ingest-Student)")
REQUEST_TIMEOUT = int(os.getenv("RAG_REQUEST_TIMEOUT", "15"))
RAW_DIR = os.getenv("RAG_RAW_DIR", "data/raw")
PROCESSED_DIR = os.getenv("RAG_PROCESSED_DIR", "data/processed/day2")
URL_SNAPSHOT = os.getenv("RAG_URL_SNAPSHOT", "0") == "1"

def _md5(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()

# --- TODO[Step B1-1]: PDF → 텍스트 추출 ---
def read_text_from_pdf(path: str) -> str:
    """
    요구사항:
    - pypdf.PdfReader로 페이지 순회
    - extract_text() 결과를 '\n'로 이어붙여 문자열 반환
    - 실패한 페이지는 빈 문자열로 대체
    """
    # TODO: 아래를 구현
    text_pages = []
    with open(path, "rb") as f:
        pdf = PdfReader(f)
        for page in pdf.pages:
            try:
                text_pages.append(page.extract_text() or "")
            except Exception:
                text_pages.append("")
    return "\n".join(text_pages)

# --- TODO[Step B1-2]: URL → 텍스트 추출 ---
def read_text_from_url(url: str, timeout: int = REQUEST_TIMEOUT) -> str:
    """
    요구사항:
    - requests.get(url, headers={'User-Agent': USER_AGENT}, timeout=timeout)
    - BeautifulSoup로 파싱하고 script/style/noscript 제거
    - soup.get_text(' ', strip=True) → 공백 정규화(r'\s+' → ' ')
    - URL_SNAPSHOT=1이면 RAW_DIR/url_snapshots/에 txt로 저장
    """
    # TODO: 아래를 구현
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    if URL_SNAPSHOT:
        out_dir = Path(RAW_DIR) / "url_snapshots"
        out_dir.mkdir(parents=True, exist_ok=True)
        safe = _md5(url) + ".txt"
        (out_dir / safe).write_text(text, encoding="utf-8", errors="ignore")
    return text

# --- TODO[Step B1-3]: 단일 소스 자동 판별 ---
def read_text_auto(src: str) -> Dict:
    """
    입력: 파일 경로(.pdf/.txt/.md 등) 또는 http(s) URL
    출력: {'text': <str>, 'meta': {'source':<str>, 'type':<str>, 'title':<str>}}
    - URL이면 type='url', title=src
    - 파일이면 type=확장자(점 제거), title=파일명
    """
    if src.startswith(("http://", "https://")):
        txt = read_text_from_url(src)
        meta = {"source": src, "type": "url", "title": src}
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

# --- TODO[Step B1-4]: 청크 분할 ---
def chunk_text(text: str, chunk_size: int = 800, overlap: int = 200) -> List[str]:
    """
    요구사항:
    - 공백 정규화(re.sub) 후 슬라이딩 윈도우로 자르기
    - 길이 0인 청크는 제외
    - 예) 0:800, 600:1400, ... (overlap=200)
    """
    text = re.sub(r"\s+", " ", text).strip()
    chunks = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + chunk_size, n)
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk)
        if end == n:
            break
        start = max(0, end - overlap)
    return chunks

# --- TODO[Step B1-5]: 여러 소스를 인제스트 ---
def ingest_sources(sources: List[str], out_dir: str | None = None) -> List[Dict]:
    """
    반환: [{id, text, source, page, kind, title}, ...]
    - id = md5(source + '::' + page_idx)
    - out_dir 기본값은 PROCESSED_DIR
    - 완료 후 out_dir/chunks.jsonl로 저장(한 줄에 하나의 JSON)
    """
    out_dir = out_dir or PROCESSED_DIR
    os.makedirs(out_dir, exist_ok=True)

    all_chunks: List[Dict] = []
    for src in sources:
        data = read_text_auto(src)
        parts = chunk_text(data["text"])
        for i, c in enumerate(parts):
            cid = _md5(f"{data['meta']['source']}::{i}")
            all_chunks.append({
                "id": cid,
                "text": c,
                "source": data["meta"]["source"],
                "page": i + 1,
                "kind": data["meta"]["type"],
                "title": data["meta"]["title"],
            })

    with open(os.path.join(out_dir, "chunks.jsonl"), "w", encoding="utf-8") as f:
        for ch in all_chunks:
            f.write(json.dumps(ch, ensure_ascii=False) + "\n")
    return all_chunks
