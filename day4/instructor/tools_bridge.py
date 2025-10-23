"""
Day1/Day2/Day3 모듈을 하나의 공통 인터페이스로 감싸는 브릿지.
- run_research(query) -> {report_md, citations, top_results, rag_schema_contexts, trace}
- run_rag(query,k)    -> {answer_md, contexts, citations, trace}
- run_government(...) -> {digest_md, notices, trace}
"""
import os, re, time, inspect
from typing import List, Dict, Any

# ======================================================================
# Day1: Web Search + URL Summarize
# ======================================================================
from day1.instructor.tools import WebSearchTool, SummarizeUrlTool
from day1.instructor.agents import summarize_text

def run_research(query: str, top_n: int = 5, summarize_top: int = 2) -> Dict[str, Any]:
    """
    return 예시:
    {
      "report_md": "...",
      "citations": [...],
      "top_results": [...],          # 원본 엔진 결과(그대로, 기존 필드 유지)
      "rag_schema_contexts": [...],  # [NEW] 표준화된 컨텍스트
      "trace": {...}
    }
    """
    search = WebSearchTool(top_k=top_n)
    results = search.run(query) or []

    s_tool = SummarizeUrlTool(summarize_text)
    summaries = []
    for r in results[:summarize_top]:
        try:
            s = s_tool.run(r["url"])
            summaries.append({
                "title": r["title"],
                "url": r["url"],
                "summary": s.get("summary","")
            })
        except Exception as e:
            summaries.append({
                "title": r["title"],
                "url": r["url"],
                "summary": f"(summary failed) {e}"
            })
        time.sleep(0.1)

    lines = [f"## Research Summary", ""]
    for i, s in enumerate(summaries, 1):
        lines.append(f"**{i}. [{s['title']}]({s['url']})**")
        lines.append(f"> {s['summary'][:600]}".strip())
        lines.append("")

    citations = [{"id": f"ref{i+1}", "title": r["title"], "url": r["url"]}
                 for i, r in enumerate(results[:top_n])]
    report_md = "\n".join(lines) if summaries else "_No summaries_"
    trace = {"saved": [], "module": "day1"}

    # [NEW] 웹 결과 → RAG 표준 스키마로 정규화
    rag_like = normalize_to_rag_schema(results)

    return {
        "report_md": report_md,
        "citations": citations,
        "top_results": results,          # (기존 유지)
        "rag_schema_contexts": rag_like, # [NEW]
        "trace": trace
    }


# ======================================================================
# Day2: RAG
# ======================================================================
from day2.instructor.rag_store import FaissStore
from day2.instructor.agents import answer_with_context  # non-stream

def run_rag(query: str, k: int = 5) -> Dict[str, Any]:
    index_dir = os.getenv("D2_INDEX_DIR", "data/processed/day2/faiss")
    store = FaissStore.load_or_new(index_dir=index_dir)

    ctx = store.search(query, k=k) if store.ntotal() > 0 else []
    answer = answer_with_context(query, ctx) if ctx else "_no local context_"

    # 표준 스키마 기준 인용 생성
    citations = []
    for i, c in enumerate(ctx, 1):
        citations.append({
            "id": f"kb{i}",
            "title": c.get("title") or f"doc{i}",
            "url": c.get("url") or c.get("source") or ""
        })

    trace = {"ntotal": store.ntotal(), "module": "day2"}
    return {"answer_md": answer, "contexts": ctx, "citations": citations, "trace": trace}


# ======================================================================
# Day3: Government (NIPA) — fetcher/ ranker 시그니처 자동 매핑
# ======================================================================

# fetcher를 어떤 이름/시그니처로 제공하든 안전하게 로드
try:
    from day3.instructor.fetchers import fetch_nipa_list_by_query as _fetch_nipa
except Exception:
    try:
        from day3.instructor.fetchers import fetch_nipa_list as _fetch_nipa
    except Exception:
        _fetch_nipa = None  # 런타임 가드

from day3.instructor.normalize import normalize_items, deduplicate

# ranker가 없는 환경 대비 기본 랭커 제공 (시그니처가 다를 수 있으므로 아래에서 래핑)
try:
    from day3.instructor.ranker import rank_items as _rank_items
except Exception:
    def _rank_items(query, items, keywords=None, w_kw=0.7, w_recency=0.3, base_year=2025):
        keys = [t for t in re.findall(r"[가-힣A-Za-z0-9]{2,}", (query or "").lower())
                if t not in {"공고","사업","지원"}]
        ranked=[]
        for it in items:
            text = (it.get("title","")+ " " + it.get("snippet","")).lower()
            s = sum(1 for k in keys if k in text)
            kw = min(1.0, s / max(1, len(keys))) if keys else 0.0
            try:
                y = int((it.get("announce_date") or "0")[:4])
            except Exception:
                y = 0
            rec = 0.3 if y >= base_year else 0.0
            it = dict(it); it["score"] = w_kw*kw + w_recency*rec
            ranked.append(it)
        ranked.sort(key=lambda x:x["score"], reverse=True)
        return ranked

def _extract_keywords(q: str, max_k: int = 6) -> List[str]:
    """
    질의에서 간단 키워드 추출 (한/영/숫자 2자 이상, 흔한 불용어 제외)
    fetcher가 keywords 파라미터를 요구할 때 사용.
    """
    if not q:
        return []
    toks = re.findall(r"[가-힣A-Za-z0-9]{2,}", q.lower())
    stop = {"최신","최근","정보","찾아줘","요약","정리","사업","지원","공고"}
    out = [t for t in toks if t not in stop]
    seen=set(); uniq=[]
    for t in out:
        if t in seen: continue
        seen.add(t); uniq.append(t)
    return uniq[:max_k] or toks[:max_k]

def _call_nipa_fetcher(fetcher, query: str, list_url: str, max_pages: int, body_limit: int):
    """
    fetcher 시그니처가 환경마다 달라서 '있는 파라미터만' 매핑해 호출.
    지원 후보 키:
      - query / q
      - list_url / url / base_url
      - max_pages / pages
      - body_limit / bytes_limit
      - keywords (일부 구현은 필수)
    """
    if fetcher is None:
        return []

    sig = inspect.signature(fetcher)
    params = set(sig.parameters.keys())

    kwargs = {}
    # 질의
    if "query" in params:
        kwargs["query"] = query
    elif "q" in params:
        kwargs["q"] = query
    # URL
    if "list_url" in params:
        kwargs["list_url"] = list_url
    elif "url" in params:
        kwargs["url"] = list_url
    elif "base_url" in params:
        kwargs["base_url"] = list_url
    # 페이지
    if "max_pages" in params:
        kwargs["max_pages"] = max_pages
    elif "pages" in params:
        kwargs["pages"] = max_pages
    # 본문 바이트 제한
    if "body_limit" in params:
        kwargs["body_limit"] = body_limit
    elif "bytes_limit" in params:
        kwargs["bytes_limit"] = body_limit
    # 키워드 (필수 구현 대응)
    if "keywords" in params:
        kwargs["keywords"] = _extract_keywords(query)

    # 호출
    return fetcher(**kwargs)

def _call_rank_items(ranker, query: str, items: List[Dict], keywords: List[str], base_year: int,
                     w_kw: float = 0.7, w_recency: float = 0.3, top_n: int | None = None) -> List[Dict]:
    """
    ranker 시그니처가 환경마다 달라서 '있는 파라미터만' 매핑해 호출.
    후보 키: query, items, keywords, base_year, w_kw, w_recency, top_n
    """
    if ranker is None:
        return items

    sig = inspect.signature(ranker)
    params = set(sig.parameters.keys())

    kwargs = {}
    if "query" in params: kwargs["query"] = query
    if "items" in params: kwargs["items"] = items
    if "keywords" in params: kwargs["keywords"] = keywords
    if "base_year" in params: kwargs["base_year"] = base_year
    if "w_kw" in params: kwargs["w_kw"] = w_kw
    if "w_recency" in params: kwargs["w_recency"] = w_recency
    if "top_n" in params and top_n is not None: kwargs["top_n"] = top_n

    ranked = ranker(**kwargs)

    # ranker가 점수 필드를 안 주는 경우 대비: 간단 점수 보정
    if ranked and isinstance(ranked[0], dict) and "score" not in ranked[0]:
        for it in ranked:
            it["score"] = it.get("score", 0.0)
    return ranked

def run_government(query: str, pages: int = 1, items: int = 3, base_year: int = 2025) -> Dict[str, Any]:
    """
    반환:
      {"digest_md": str, "notices": List[dict], "trace": dict}
    notices는 formatter 스키마에 맞춰 사용됨:
      title, url, agency, announce_date, close_date, budget, program_type,
      eligibility, requirements, attachments, content_type, score
    """
    list_url = os.getenv("NIPA_LIST_URL","https://www.nipa.kr/home/2-2")
    body_limit = int(os.getenv("NIPA_PER_ITEM_BYTES","900"))

    # ✅ 시그니처 자동 매핑으로 안전 호출
    raw = _call_nipa_fetcher(_fetch_nipa, query, list_url, pages, body_limit)

    pool = deduplicate(normalize_items(raw, "government"))
    ranked = _call_rank_items(_rank_items, query, pool, [], base_year, w_kw=0.7, w_recency=0.3)[:items]

    def _render_digest(lst: List[Dict]) -> str:
        text_items = [x for x in lst if x.get("content_type")=="text"]
        attach_items = [x for x in lst if x.get("content_type")=="attachment"]
        out = ["## Government Digest", ""]
        if text_items:
            out.append("### 텍스트 중심 공고")
            for i, it in enumerate(text_items, 1):
                out.append(f"**{i}. [{it.get('title','')}]({it.get('url','')})**")
                meta=[]
                for k in ["announce_date","close_date","agency","budget"]:
                    if it.get(k): meta.append(f"{k}: {it[k]}")
                if meta: out.append("- " + " / ".join(meta))
                if it.get("summary"): out.append("> " + it["summary"][:400])
                if it.get("attachments"):
                    out.append("- 첨부:")
                    for a in it["attachments"][:6]:
                        out.append(f"  - [{a.get('name','file')}]({a.get('url','')})")
                out.append("")
        if attach_items:
            out.append("### 첨부 중심 공고")
            for i, it in enumerate(attach_items, 1):
                out.append(f"**{i}. [{it.get('title','')}]({it.get('url','')})**")
                meta=[]
                for k in ["announce_date","close_date","agency","budget"]:
                    if it.get(k): meta.append(f"{k}: {it[k]}")
                if meta: out.append("- " + " / ".join(meta))
                if it.get("attachments"):
                    out.append("- 첨부(공고문/양식):")
                    for a in it["attachments"][:8]:
                        out.append(f"  - [{a.get('name','file')}]({a.get('url','')})")
                out.append("")
        if not text_items and not attach_items:
            out.append("_조건에 맞는 공고 없음_")
        return "\n".join(out)

    digest_md = _render_digest(ranked)
    # ✅ formatter 스키마에 맞춘 필드 확장
    notices = [{
        "title": it.get("title"),
        "url": it.get("url"),
        "announce_date": it.get("announce_date"),
        "close_date": it.get("close_date"),
        "agency": it.get("agency"),
        "budget": it.get("budget"),
        "program_type": it.get("program_type"),
        "eligibility": it.get("eligibility"),
        "requirements": it.get("requirements"),
        "attachments": it.get("attachments", []),
        "content_type": it.get("content_type","text"),
        "score": it.get("score"),
    } for it in ranked]

    trace = {
        "count": len(ranked),
        "module": "day3",
        "fetcher": getattr(_fetch_nipa, "__name__", "unknown"),
        "ranker": getattr(_rank_items, "__name__", "unknown"),
    }
    return {"digest_md": digest_md, "notices": notices, "trace": trace}


# ======================================================================
# 공통: 웹 결과를 RAG 컨텍스트 스키마로 정규화
# ======================================================================
def normalize_to_rag_schema(web_results: list[dict]) -> list[dict]:
    """
    웹 검색 결과를 RAG 스키마로 변환.
    기대되는 원본 키(엔진별 다양): title, url, snippet, content, site, domain, score, id
    출력: {id,title,url,source,summary,text,page,kind,score}
    """
    norm = []
    for r in web_results or []:
        title = (r.get("title") or "").strip()
        url = (r.get("url") or "").strip()
        site = r.get("site") or r.get("domain") or ""
        snippet = r.get("snippet") or r.get("summary") or ""
        content = r.get("content") or snippet
        score = float(r.get("score", 0.2))  # 웹은 기본 낮은 점수로 시작

        norm.append({
            "id": r.get("id") or url or title,
            "title": title,
            "url": url,
            "source": site,
            "summary": snippet,
            "text": content,
            "page": None,
            "kind": "web",
            "score": score,
        })
    return norm
