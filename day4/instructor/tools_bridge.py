import os, time, re
from typing import Dict, Any, List

# ---------- Day1 ----------
from day1.instructor.tools import WebSearchTool, SummarizeUrlTool
from day1.instructor.agents import summarize_text

def run_research(query: str, top_n: int = 5, summarize_top: int = 2) -> Dict[str, Any]:
    search = WebSearchTool(top_k=top_n)
    results = search.run(query) or []
    s_tool = SummarizeUrlTool(summarize_text)
    sums=[]
    for r in results[:summarize_top]:
        try:
            s = s_tool.run(r["url"])
            sums.append({"title": r["title"], "url": r["url"], "summary": s.get("summary","")})
        except Exception as e:
            sums.append({"title": r["title"], "url": r["url"], "summary": f"(summary failed) {e}"})
        time.sleep(0.1)
    lines=["## Research Summary",""]
    for i, s in enumerate(sums,1):
        lines += [f"**{i}. [{s['title']}]({s['url']})**", f"> {s['summary'][:600]}", ""]
    cits = [{"id":f"ref{i+1}","title":r["title"],"url":r["url"]} for i, r in enumerate(results[:top_n])]
    return {"report_md":"\n".join(lines) if sums else "_No summaries_", "citations":cits, "top_results":results}

# ---------- Day2 ----------
from day2.instructor.rag_store import FaissStore
from day2.instructor.agents import answer_with_context

def run_rag(query: str, k: int = 5) -> Dict[str, Any]:
    store = FaissStore.load_or_new(index_dir=os.getenv("D2_INDEX_DIR","data/processed/day2/faiss"))
    ctx = store.search(query, k=k) if store.ntotal() > 0 else []
    ans = answer_with_context(query, ctx) if ctx else "_no local context_"
    cits=[]
    for i, c in enumerate(ctx,1):
        cits.append({"id":f"kb{i}","title":c.get("title") or f"doc{i}","url":c.get("url") or c.get("source","")})
    return {"answer_md":ans,"contexts":ctx,"citations":cits,"trace":{"ntotal":store.ntotal()}}

# ---------- Day3 ----------
from day3.instructor.fetchers import fetch_nipa_list_by_query, search_web_notices
from day3.instructor.normalize import normalize_items, deduplicate
from day3.instructor.ranker import rank_notices
from day3.instructor.agents import render_digest

def _extract_keywords(q: str, top_n: int = 6):
    toks = re.findall(r"[가-힣A-Za-z0-9]{2,}", (q or "").lower())
    stop = {"그리고","또는","및","관련","대한","에서","으로","하는","에","의","을","를","은","는","이","가",
            "좀","알려줘","찾아줘","사업","공고","모집","지원","사업공고","최신","최근"}
    toks = [t for t in toks if t not in stop]
    out=[]; seen=set()
    for t in toks:
        if t in seen: continue
        seen.add(t); out.append(t)
        if len(out)>=top_n: break
    return out

def run_government(query: str, pages: int = 1, items: int = 10, base_year: int = 2025) -> Dict[str, Any]:
    kw = _extract_keywords(query)
    gov_nipa = fetch_nipa_list_by_query(kw, max_pages=pages)
    gov_web  = search_web_notices(query, top_n=6)

    pool = deduplicate(normalize_items(gov_nipa, "government") + normalize_items(gov_web, "government"))
    ranked = rank_notices(query, pool, kw, w_deadline=0.6, w_sim=0.25, w_kw=0.15)

    # 정책: NIPA top3 + Web top2 (부족 시 ranked로 보충)
    nipa = [it for it in ranked if it.get("source")=="gov-nipa"][:3]
    web  = [it for it in ranked if it.get("source")!="gov-nipa"][:2]
    final = nipa + web
    if len(final) < min(items, 5):
        for it in ranked:
            if it in final: continue
            final.append(it)
            if len(final) >= min(items, 5): break

    digest_md = render_digest(final, kw)
    notices = [{
        "title": it.get("title"), "url": it.get("url"),
        "announce_date": it.get("announce_date"), "close_date": it.get("close_date"),
        "agency": it.get("agency"), "budget": it.get("budget"),
        "attachments": it.get("attachments", []), "content_type": it.get("content_type","text"),
        "source": it.get("source"), "score": it.get("score")
    } for it in final]
    return {"digest_md":digest_md, "notices":notices, "trace":{"pool":len(pool),"ranked":len(ranked)}}
