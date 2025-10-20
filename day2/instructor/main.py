import os, json, glob
from datetime import datetime
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(), override=False)

from day2.instructor.ingest import ingest_sources
from day2.instructor.rag_store import FaissStore
from day2.instructor.agents import answer_with_context, answer_with_context_stream

# Day 1의 websearchtool 재활용
try:
    from day1.instructor.tools import WebSearchTool
except Exception:
    WebSearchTool = None

# ---------- 유틸: 폴더에서 소스 자동 수집 ----------
def collect_sources_from_folder(
    raw_dir: str,
    allowed_exts: tuple[str, ...] = ("pdf", "txt", "md"),
    urls_file: str | None = None,
    recursive: bool = True,
) -> list[str]:
    """
    raw_dir 하위의 allowed_exts 파일들을 모두 찾고,
    urls_file(기본: raw_dir/urls.txt)에 http/https 링크가 있으면 함께 반환.
    """
    paths = []
    # 파일 수집
    pattern = "**/*" if recursive else "*"
    for ext in allowed_exts:
        paths.extend(glob.glob(os.path.join(raw_dir, f"{pattern}.{ext}"), recursive=recursive))

    # URL 목록 수집 (data/raw/urls.txt파일에 주소가 있으면 해당 주소 탐색)
    if urls_file is None:
        urls_file = os.path.join(raw_dir, "urls.txt")
    if os.path.exists(urls_file):
        with open(urls_file, "r", encoding="utf-8") as f:
            for line in f:
                url = line.strip()
                if url.startswith(("http://", "https://")):
                    paths.append(url)

    # 중복 제거 및 정렬
    seen = set()
    uniq = []
    for p in paths:
        if p not in seen:
            uniq.append(p)
            seen.add(p)
    # 파일은 존재하는 것만, URL은 그대로
    final = [p for p in uniq if (p.startswith("http") or os.path.exists(p))]
    return sorted(final)

# ---------- 표 렌더 ----------
def render_hits_table(hits):
    lines = ["| # | 제목 | 점수 | 출처 |", "|---:|---|---:|---|"]
    for i, h in enumerate(hits, 1):
        title = (h.get("title") or "").replace("|", " ")
        url = h.get("source", "")
        score = f"{h.get('score', 0):.3f}"
        lines.append(f"| {i} | [{title}]({url}) | {score} | `{url}` |")
    return "\n".join(lines)

def render_web_table(results):
    if not results:
        return "(no web results)"
    lines = ["| # | 제목 | 도메인 | 요약 |", "|---:|---|---|---|"]
    for i, r in enumerate(results, 1):
        title = (r.get("title") or "").replace("|", " ")
        url = r.get("url") or ""
        domain = url.split("/")[2] if "://" in url else "example.com"
        snippet = (r.get("snippet") or "").replace("\n", " ").strip()[:120]
        lines.append(f"| {i} | [{title}]({url}) | `{domain}` | {snippet} |")
    return "\n".join(lines)

# ---------- 메인 파이프라인 ----------
def smoke_ingest_and_qa():
    print("=== Day2 RAG Smoke (Instructor) ===")
    RAW_DIR = os.getenv("RAG_RAW_DIR", "data/raw")
    PROCESSED_DIR = os.getenv("RAG_PROCESSED_DIR", "data/processed/day2")
    USE_STREAM = os.getenv("RAG_STREAM", "1") == "1"
    exts_env = os.getenv("RAG_EXTS", "pdf,txt,md")
    allowed_exts = tuple(e.strip().lstrip(".").lower() for e in exts_env.split(",") if e.strip())

    # 1) 폴더에서 소스 자동 수집
    sources = collect_sources_from_folder(RAW_DIR, allowed_exts=allowed_exts, urls_file=None, recursive=True)
    if not sources:
        print(f"[WARN] No sources found under '{RAW_DIR}' (exts={allowed_exts})")
        print(" - Put files under the folder or create data/raw/urls.txt with http(s) links.")
        return

    print("[INGEST SOURCES]")
    for s in sources:
        tag = "URL " if s.startswith("http") else "FILE"
        print(f" - ({tag}) {s}")

    # 2) 인제스트 → 업서트
    chunks = ingest_sources(sources, out_dir=PROCESSED_DIR)
    print(f"[INGEST] total chunks created this run: {len(chunks)}")
    store = FaissStore(dirpath=PROCESSED_DIR)
    total, added = store.upsert(chunks)
    print(f"[FAISS] total: {total}, added this run: {added}")

    # 3) 질문 → Retrieval 검색
    question = os.getenv("RAG_QUESTION", "의료영상 AI 규제의 핵심 포인트는?")
    hits = store.search(question, k=5)

    # 4) (옵션) Web Search도 함께
    web_results = []
    if WebSearchTool:
        try:
            web_results = WebSearchTool(top_k=3).run(question)
        except Exception as e:
            web_results = [{"title": "[WEB ERROR]", "url": "", "snippet": str(e)}]

    # 5) 화면 출력(두 표를 모두)
    print(f"\n[Retrieval Hits Top-{len(hits)}]")
    print(render_hits_table(hits))
    print(f"\n[Web Search Top-{len(web_results)}]")
    print(render_web_table(web_results))

    # 6) 답변 (로컬 RAG 컨텍스트 우선) — 스트리밍 옵션
    print("\n[Answer]")
    if USE_STREAM:
        ans = answer_with_context_stream(question, hits, k_refs=3)  # 스트리밍
    else:
        ans = answer_with_context(question, hits, k_refs=3)
        print(ans)

    # 7) 보고서 저장
    os.makedirs("data/processed", exist_ok=True)
    md = []
    md.append(f"# Day2 RAG Snapshot — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    md.append(f"- **Question**: {question}")
    md.append(f"- **RAW_DIR**: `{RAW_DIR}` | **EXTS**: {', '.join(allowed_exts)}")
    md.append("\n## Retrieval Hits")
    md.append(render_hits_table(hits))
    md.append("\n## Web Search")
    md.append(render_web_table(web_results))
    md.append("\n## Answer (with citations)")
    md.append(ans)
    out_path = "data/processed/day2_snapshot.md"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    print(f"\n[Saved] {out_path}")

if __name__ == "__main__":
    smoke_ingest_and_qa()
