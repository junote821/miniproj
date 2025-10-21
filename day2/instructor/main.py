import os
from datetime import datetime
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(), override=False)

from day2.instructor.ingest import ingest_sources, collect_sources_from_folder
from day2.instructor.rag_store import FaissStore
from day2.instructor.agents import answer_with_context

def render_hits_table(items, title="RAG Retrieval"):
    lines = [f"### {title}", "| # | 제목 | 점수 | 출처 |", "|---:|---|---:|---|"]
    for i, it in enumerate(items, 1):
        lines.append(
            f"| {i} | {it.get('title','')} | {it.get('score',0):.3f} | `{it.get('source','')}` |"
        )
    return "\n".join(lines)

def main():
    print("=== Day2 (Instructor) — Local RAG ===")
    query = os.getenv("D2_QUERY", "헬스케어 AI 임상 적용 사례 알려줘")

    # 1) 수집/청크 생성
    paths = collect_sources_from_folder(os.getenv("RAG_RAW_DIR", "data/raw"))
    chunks = ingest_sources(paths, chunk_size=800, overlap=100, kind="healthcare")

    # 2) 업서트
    store = FaissStore()
    total, added = store.upsert(chunks)
    print(f"[RAG] ntotal={total}, added={added}")

    # 3) 검색/답변
    hits = store.search(query, k=6)
    print(render_hits_table(hits, "RAG Retrieval (Top-6)"))
    print("\n[Answer]")
    ans = answer_with_context(query, hits, k_refs=3)
    print(ans)

    # 4) 저장
    os.makedirs("data/processed", exist_ok=True)
    out_path = "data/processed/day2_snapshot_instructor.md"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"# Day2 Snapshot — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"- Query: {query}\n\n")
        f.write(render_hits_table(hits, "RAG Retrieval (Top-6)") + "\n\n")
        f.write("## Final Answer\n" + ans + "\n")
    print(f"[Saved] {out_path}")

if __name__ == "__main__":
    main()
