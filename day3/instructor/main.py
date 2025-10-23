import os, re, json
from datetime import datetime
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(), override=False)

from day3.instructor.fetchers import fetch_nipa_list_by_query, search_web_notices
from day3.instructor.normalize import normalize_items, deduplicate
from day3.instructor.ranker import rank_notices
from day3.instructor.agents import render_digest

# (옵션) Day2 RAG 업서트
from day2.instructor.rag_store import FaissStore

STOP = {"그리고","또는","및","관련","대한","에서","으로","하는","에","의","을","를","은","는","이","가",
        "좀","알려줘","찾아줘","사업","공고","모집","지원","사업공고","최신","최근"}

def extract_keywords(q: str, top_n: int = 6):
    toks = re.findall(r"[가-힣A-Za-z0-9]{2,}", (q or "").lower())
    toks = [t for t in toks if t not in STOP]
    seen, out = set(), []
    for t in toks:
        if t in seen: continue
        seen.add(t); out.append(t)
        if len(out) >= top_n: break
    return out

def to_rag_chunks(items, kind="government"):
    return [{
        "id": it.get("id") or (it.get("url","")+"|"+it.get("title","")),
        "text": (it.get("title","") + "\n" + (it.get("summary") or it.get("snippet",""))).strip(),
        "source": it.get("url",""),
        "page": 1,
        "kind": kind,
        "title": it.get("title",""),
    } for it in items]

def render_table(items, title="TABLE"):
    lines = [f"### {title}", "| # | 제목 | 마감일 | 점수 | 출처 |", "|---:|---|---:|---:|---|"]
    for i, it in enumerate(items, 1):
        score = f"{it.get('score', 0):.3f}"
        lines.append(f"| {i} | [{it['title']}]({it.get('url','')}) | {it.get('close_date','-')} | {score} | `{it.get('source','')}` |")
    return "\n".join(lines)

def main():
    print("=== Day3 (Instructor) — NIPA + Web hybrid ===")
    query = os.getenv("D3_QUERY", "최신 클라우드 사업공고를 찾아줘")
    max_pages = int(os.getenv("NIPA_MAX_PAGES", "1"))
    items_nipa = 3   # NIPA 상위 3
    items_web  = 2   # 웹 상위 2

    # 1) 키워드
    keywords = extract_keywords(query)
    print("Keywords:", keywords)

    # 2) NIPA 수집
    print("[RUN] NIPA collect…")
    gov_nipa = fetch_nipa_list_by_query(keywords, max_pages=max_pages)

    # 3) Web 수집
    print("[RUN] Web collect…")
    gov_web = search_web_notices(query, top_n=6)

    # 4) 정규화/중복 제거
    pool = deduplicate(normalize_items(gov_nipa, "government") + normalize_items(gov_web, "government"))
    print(f"[RUN] merged pool: {len(pool)}")

    # 5) 랭킹: 마감 임박 우선 + 의미 유사도 + 키워드 적합도
    ranked = rank_notices(query, pool, keywords, w_deadline=0.55, w_sim=0.30, w_kw=0.15)

    # 6) NIPA 우선에서 상위 3, Web에서 상위 2 선별
    nipa_only = [it for it in ranked if (it.get("source") == "gov-nipa")]
    web_only  = [it for it in ranked if (it.get("source") != "gov-nipa")]
    top_final = (nipa_only[:items_nipa]) + (web_only[:items_web])

    # 7) Digest
    digest_md = render_digest(top_final, keywords)

    # 8) (옵션) Day2 RAG 업서트
    if os.getenv("D3_UPSERT_RAG","1") == "1":
        store = FaissStore()
        ch = to_rag_chunks(top_final)
        ntotal, added = store.upsert(ch)
        print(f"[RAG] upsert → ntotal={ntotal}, added={added}")

    # 9) 저장
    os.makedirs("data/processed", exist_ok=True)
    md_path = "data/processed/day3_snapshot.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# Day3 Snapshot — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"- Query: {query}\n- Policy: NIPA top {items_nipa} + Web top {items_web}\n\n")
        f.write(render_table(ranked[:12], "Ranked (Top-12)") + "\n\n")
        f.write("## Digest\n" + digest_md + "\n")
    print(f"[Saved] {md_path}")

    json_path = "data/processed/day3_notices.json"
    with open(json_path, "w", encoding="utf-8") as jf:
        json.dump({
            "query": query,
            "generated_at": datetime.now().isoformat(),
            "policy": {"nipa": items_nipa, "web": items_web},
            "notices": [{
                "title": it.get("title"),
                "url": it.get("url"),
                "announce_date": it.get("announce_date"),
                "close_date": it.get("close_date"),
                "agency": it.get("agency"),
                "budget": it.get("budget"),
                "attachments": it.get("attachments", []),
                "requirements": it.get("requirements"),
                "content_type": it.get("content_type","text"),
                "score": it.get("score")
            } for it in top_final]
        }, jf, ensure_ascii=False, indent=2)
    print(f"[Saved] {json_path}")

if __name__ == "__main__":
    main()
