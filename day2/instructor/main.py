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
    index_dir = os.getenv("D2_INDEX_DIR", "data/processed/day2/faiss")
    raw_dir = os.getenv("RAG_RAW_DIR", "data/raw")
    query = os.getenv("D2_QUERY", "헬스케어 AI 최신 규제 사례 알려줘")

    store = FaissStore.load_or_new(index_dir)

    # 0) 인덱스 준비
    if store.ntotal() == 0:
        sources = collect_sources_from_folder(raw_dir)
        chunks = ingest_sources(sources, out_dir=index_dir, kind="instructor")
        ntotal, added = store.upsert(chunks)
        print(f"[Upsert] ntotal={ntotal}, added={added}")
    else:
        print(f"[Index ready] ntotal={store.ntotal()}")

    # 1) 검색
    k = int(os.getenv("D2_TOPK", "6"))
    hits = store.search(query, k=k)
    print(render_hits_table(hits, f"RAG Retrieval (Top-{k})"))

    # 2) 답변
    ans = answer_with_context(query, hits, k_refs=int(os.getenv("D2_K_REFS","3")))
    print(ans)

    # 3) 스냅샷 저장
    os.makedirs("data/processed", exist_ok=True)
    out_path = "data/processed/day2_snapshot_instructor.md"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"# Day2 Snapshot — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"- Query: {query}\n\n")
        f.write(render_hits_table(hits, f"RAG Retrieval (Top-{k})") + "\n\n")
        f.write("## Final Answer\n" + ans + "\n")
    print(f"[Saved] {out_path}")

if __name__ == "__main__":
    main()
