# Day2 스캐폴딩
# 목적: 폴더 자동 스캔 → ingest → upsert → search → (선택) web search → 표 출력 → QA
# 프로젝트의 흐름/출력 구조를 따르되, 핵심 호출은 여러분이 연결 직접 연결해보세요.

import os, glob
from datetime import datetime
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(), override=False)

from day2.student.ingest import ingest_sources
from day2.student.rag_store import FaissStore
from day2.student.agents import answer_with_context

# (선택) Day1의 WebSearchTool 사용 가능
try:
    from day1.student.tools import WebSearchTool
except Exception:
    WebSearchTool = None

def collect_sources_from_folder(
    raw_dir: str,
    allowed_exts: tuple[str, ...] = ("pdf", "txt", "md"),
    urls_file: str | None = None,
    recursive: bool = True,
) -> list[str]:
    paths = []
    pattern = "**/*" if recursive else "*"
    for ext in allowed_exts:
        paths.extend(glob.glob(os.path.join(raw_dir, f"{pattern}.{ext}"), recursive=recursive))
    if urls_file is None:
        urls_file = os.path.join(raw_dir, "urls.txt")
    if os.path.exists(urls_file):
        for line in open(urls_file, "r", encoding="utf-8"):
            u = line.strip()
            if u.startswith(("http://", "https://")):
                paths.append(u)
    
    # 중복 제거 + 존재 확인
    seen, uniq = set(), []
    for p in paths:
        if p not in seen:
            uniq.append(p); seen.add(p)
    final = [p for p in uniq if (p.startswith("http") or os.path.exists(p))]
    return sorted(final)

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

def smoke_ingest_and_qa():
    print("=== Day2 RAG Smoke (Student / Scaffold) ===")
    RAW_DIR = os.getenv("RAG_RAW_DIR", "data/raw")
    PROCESSED_DIR = os.getenv("RAG_PROCESSED_DIR", "data/processed/day2")
    exts_env = os.getenv("RAG_EXTS", "pdf,txt,md")
    allowed_exts = tuple(e.strip().lstrip(".").lower() for e in exts_env.split(",") if e.strip())

    # 1) 폴더 자동 스캔
    sources = collect_sources_from_folder(RAW_DIR, allowed_exts=allowed_exts)
    print("[INGEST SOURCES]")
    for s in sources:
        tag = "URL " if s.startswith("http") else "FILE"
        print(f" - ({tag}) {s}")
    if not sources:
        print(f"[WARN] No sources found under '{RAW_DIR}'")
        return

    # 2) TODO[연결]: 인제스트 → 업서트
    chunks = ingest_sources(sources, out_dir=PROCESSED_DIR)  # TODO: 구현 완료 후 라인 수 출력
    store = FaissStore(dirpath=PROCESSED_DIR)
    total, added = store.upsert(chunks)
    print(f"[FAISS] total: {total}, added this run: {added}")

    # 3) TODO[연결]: 검색
    question = os.getenv("RAG_QUESTION", "의료영상 AI 규제의 핵심 포인트는?")
    hits = store.search(question, k=5)
    print(f"\n[Retrieval Hits Top-{len(hits)}]")
    print(render_hits_table(hits))

    # 4) (선택) Web Search 병행
    web_results = []
    if WebSearchTool:
        try:
            web_results = WebSearchTool(top_k=3).run(question)
        except Exception as e:
            web_results = [{"title": "[WEB ERROR]", "url": "", "snippet": str(e)}]
    print(f"\n[Web Search Top-{len(web_results)}]")
    print(render_web_table(web_results))

    # 5) TODO[연결]: QA (컨텍스트는 Retrieval 우선)
    print("\n[Answer]")
    ans = answer_with_context(question, hits, k_refs=3)
    print(ans)

    # 6) 보고서 저장(선택)
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
