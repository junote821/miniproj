import os
from datetime import datetime
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(), override=False)

from day2.student.rag_store import FaissStore
from day2.student.agents import answer_with_context

INDEX_DIR = os.getenv("D2_INDEX_DIR", "data/processed/day2/faiss")

def render_hits_table(hits):
    """
    TODO-D2-12: Retrieval 결과를 마크다운 표로 렌더
    | # | 제목 | 점수 | 출처 |
    |---:|---|---:|---|
    """
    lines = ["| # | 제목 | 점수 | 출처 |", "|---:|---|---:|---|"]
    for i, h in enumerate(hits, 1):
        lines.append(f"| {i} | {h.get('title','')} | {h.get('score',0):.3f} | {h.get('source','')} |")
    return "\n".join(lines)

def smoke_ingest_and_qa():
    """
    TODO-D2-14: 인덱스 로드 → 검색 → 답변 → MD 저장
    """
    q = os.getenv("D2_QUERY", "AI 규제")
    store = FaissStore.load_or_new(index_dir=INDEX_DIR)
    hits = store.search(q, k=5)
    ans = answer_with_context(q, hits)

    md = []
    md.append(f"# Day2 Snapshot — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    md.append(f"- Query: {q}")
    md.append(f"- Index dir: {INDEX_DIR}")
    md.append("\n## Retrieval (Top-5)")
    md.append(render_hits_table(hits))
    md.append("\n## Answer")
    md.append(ans)

    os.makedirs("data/processed", exist_ok=True)
    out_path = "data/processed/day2_snapshot.md"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    print(f"[Saved] {out_path}")

if __name__ == "__main__":
    smoke_ingest_and_qa()
