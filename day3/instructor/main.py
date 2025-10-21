import os, json, re
from datetime import datetime
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(), override=False)

from day3.instructor.fetchers import fetch_nipa_list_by_query
from day3.instructor.normalize import normalize_items, deduplicate
from day3.instructor.ranker import rank_items
from day3.instructor.agents import classify_intent, render_digest

# Day2 재사용
from day2.instructor.rag_store import FaissStore

def to_rag_chunks(items, kind="government"):
    return [{
        "id": it["id"],
        "text": (it.get("title","") + "\n" + it.get("summary","")).strip(),
        "source": it.get("url",""),
        "page": 1,
        "kind": kind,
        "title": it.get("title",""),
    } for it in items]

def render_table(items, title="TABLE"):
    lines = [f"### {title}", "| # | 제목 | 점수 | 출처 |", "|---:|---|---:|---|"]
    for i, it in enumerate(items, 1):
        score = f"{it.get('score', 0):.3f}"
        lines.append(f"| {i} | [{it['title']}]({it.get('url','')}) | {score} | `{it.get('source','')}` |")
    return "\n".join(lines)

# --- 질의 키워드 추출/가산 ---
STOP = {"그리고","또는","또","및","관련","대한","에서","으로","하는","에","의","을","를","은","는","이","가","좀","좀더","알려줘","보고서","리포트","분석","사업","공고","지원","프로그램","사업공고","찾아줘"}
def extract_keywords(q: str, top_n: int = 6):
    toks = re.findall(r"[가-힣A-Za-z0-9]{2,}", (q or "").lower())
    toks = [t for t in toks if t not in STOP]
    seen, out = set(), []
    for t in toks:
        if t in seen: continue
        seen.add(t); out.append(t)
        if len(out) >= top_n: break
    return out

def keyword_score(item, keywords):
    blob = f"{item.get('title','')} {item.get('summary','')}".lower()
    atts = " ".join([(a.get("name") or "") for a in (item.get("attachments") or [])]).lower()
    text = blob + " " + atts
    if not keywords: return 0.0
    s = 0.0
    for k in keywords:
        if not k or k in STOP: continue
        if re.search(rf"\b{k}\b", text): s += 1.0
        elif k in text: s += 0.5
    denom = max(1, len([k for k in keywords if k not in STOP]))
    return min(1.0, s / denom)

def annotate_matches(items, keywords):
    for it in items:
        mf=[]
        text_blob = f"{it.get('title','')} {it.get('summary','')}".lower()
        for k in keywords:
            if k in text_blob:
                if "title/summary" not in mf: mf.append("title/summary")
                break
        for k in keywords:
            for a in it.get("attachments") or []:
                name = (a.get("name") or "").lower()
                if k in name:
                    mf.append("attachments.name"); break
            else:
                continue
            break
        it["matched_fields"] = mf or []
    return items

def main():
    print("=== Day3 (Instructor) — NIPA Government Digest (query-driven) ===")
    query = os.getenv("D3_QUERY", "SaaS 해외 진출 지원 공고 찾아줘")
    intent = classify_intent(query)
    print("Intent:", intent)

    # 1) 키워드 → 목록 수집을 '검색 파라미터'로
    q_keywords = extract_keywords(query)
    print("Query keywords:", q_keywords)
    max_pages = int(os.getenv("NIPA_MAX_PAGES", "1"))
    body_limit = int(os.getenv("NIPA_PER_ITEM_BYTES", "900"))
    print(f"[RUN] collecting via list search… pages={max_pages} body_limit={body_limit}")
    gov_items = fetch_nipa_list_by_query(q_keywords, max_pages=max_pages, body_limit=body_limit)
    print(f"[RUN] collected items: {len(gov_items)}")

    # 2) 정규화/중복/연도 필터/랭킹
    print("[RUN] normalize/dedupe/rank…")
    pool = deduplicate(normalize_items(gov_items, "government"))
    min_year = int(os.getenv("NIPA_MIN_YEAR", "2024"))
    pool = [it for it in pool if not it.get("announce_date") or int(it["announce_date"][:4]) >= min_year]

    ranked = rank_items(query, pool, w_sim=0.6, w_recency=0.4)

    # 키워드 OR 가산 + 메뉴성 타이틀 하향
    for it in ranked:
        ks = keyword_score(it, q_keywords)
        it["kw_score"] = ks
        it["score"] = it.get("score", 0.0) + 0.4 * ks
    for it in ranked:
        title = it.get("title","").strip()
        if title in {"주요사업","사업공고","사업 안내"} and not it.get("attachments"):
            it["score"] *= 0.7
    ranked.sort(key=lambda x: x.get("score",0.0), reverse=True)

    ranked = annotate_matches(ranked, q_keywords)
    print(f"[RUN] ranked: {len(ranked)}")

    # 3) RAG upsert/search
    print("[RUN] RAG upsert/search…")
    store = FaissStore()
    chunks = to_rag_chunks(ranked[:40], kind="government")
    total, added = store.upsert(chunks)
    print(f"[RAG] ntotal={total}, added={added}")
    hits = store.search(query, k=6)
    print("\n[Retrieval (Top-6)]")
    print(render_table(hits, "Government Retrieval"))

    # 4) Digest 렌더링(텍스트형/첨부형 분리 포함은 agents.render_digest에서 처리)
    top_items = ranked[:10]
    digest_md = render_digest(top_items, q_keywords)

    # 5) 저장
    print("[RUN] save snapshot…")
    os.makedirs("data/processed", exist_ok=True)
    md_path = "data/processed/day3_snapshot.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# Day3 Snapshot — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"- Query: {query}\n- Intent: {intent}\n")
        f.write(f"- NIPA_LIST_URL: https://www.nipa.kr/home/2-2\n- NIPA_MAX_PAGES: {max_pages}\n")
        f.write("\n")
        f.write(render_table(ranked[:15], "Ranked Government Items (Top-15)"))
        f.write("\n\n## Digest\n")
        f.write(digest_md + "\n")
    print(f"[Saved] {md_path}")

    json_path = "data/processed/day3_notices.json"
    digest = [{
        "title": it.get("title"),
        "url": it.get("url"),
        "announce_date": it.get("announce_date"),
        "close_date": it.get("close_date"),
        "agency": it.get("agency"),
        "budget": it.get("budget"),
        "attachments": it.get("attachments", []),
        "requirements": it.get("requirements"),
        "matched_fields": it.get("matched_fields", []),
        "score": it.get("score"),
        "summary": it.get("summary"),
        "content_type": it.get("content_type","text"),
    } for it in top_items]
    with open(json_path, "w", encoding="utf-8") as jf:
        json.dump({"query": query, "generated_at": datetime.now().isoformat(), "notices": digest},
                  jf, ensure_ascii=False, indent=2)
    print(f"[Saved] {json_path}")

if __name__ == "__main__":
    main()
