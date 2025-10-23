"""
Day1/Day2/Day3 모듈을 하나의 공통 인터페이스로 감싸는 브릿지 + 주가 스냅샷.
- run_research(query) -> {report_md, citations, top_results, rag_schema_contexts, trace}
- run_rag(query,k)    -> {answer_md, contexts, citations, trace}
- run_government(...) -> {digest_md, notices, trace}
- get_stock_snapshot(query_or_symbol) -> {symbol, price, change, change_pct, ...} or {error:...}
"""
import os, re, time, math
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(), override=False)

# ---------- Day1: Web Search + URL Summarize (동기 안전 래퍼) ----------
from day1.instructor.tools import WebSearchTool, SummarizeUrlTool
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import InMemoryRunner
from google.genai import types

MODEL_NAME = os.getenv("MODEL_NAME", "openai/gpt-4o-mini")

def _llm_summarize_sync(prompt: str) -> str:
    """ADK Web 이벤트 루프 내부에서도 안전한 '동기' 요약기."""
    agent = LlmAgent(name="d1_sync_summarizer",
                     model=LiteLlm(model=MODEL_NAME),
                     instruction="주어진 웹페이지 일부 텍스트를 4~6줄로 간결히 한국어 요약.")
    runner = InMemoryRunner(agent=agent, app_name="d1_sync_summarizer_app")
    try:
        runner.session_service.create_session_sync(app_name="d1_sync_summarizer_app",
                                                   user_id="u", session_id="sum")
    except Exception:
        pass

    out = []
    for ev in runner.run(
        user_id="u", session_id="sum",
        new_message=types.Content(role="user", parts=[types.Part(text=prompt)])
    ):
        if ev and getattr(ev, "content", None) and ev.content.parts:
            for p in ev.content.parts:
                if getattr(p, "text", None):
                    out.append(p.text)
    return ("".join(out)).strip()

def _summarize_url_sync(url: str) -> Dict[str, str]:
    """
    URL을 받아 안전하게 짧은 요약을 반환.
    SummarizeUrlTool + 동기형 LLM 요약기 조합 (비동기 금지)
    """
    try:
        # 원래 Day1의 SummarizeUrlTool은 내부 fetch + text 추출을 해줌
        s_tool = SummarizeUrlTool(lambda x: {"summary": x})  # 바디 프록시로만 사용
        fetched = s_tool.run(url)  # {"summary": <본문 일부 추출>} 형태로 들어옴
        raw = fetched.get("summary", "")[:3000]
        if not raw:
            return {"summary": "(요약 불가: 콘텐츠 추출 실패)"}
        prompt = f"아래 웹 문서를 4~6줄 한국어 불릿으로 요약:\n\n{raw}"
        return {"summary": _llm_summarize_sync(prompt)}
    except Exception as e:
        return {"summary": f"(요약 실패) {e}"}

def run_research(query: str, top_n: int = 5, summarize_top: int = 2) -> Dict[str, Any]:
    search = WebSearchTool(top_k=top_n)
    results = search.run(query) or []

    summaries = []
    for r in results[:max(0, summarize_top)]:
        s = _summarize_url_sync(r["url"])
        summaries.append({"title": r["title"], "url": r["url"], "summary": s.get("summary","")})
        time.sleep(0.05)

    lines = [f"## Research Summary", ""]
    for i, s in enumerate(summaries, 1):
        lines.append(f"**{i}. [{s['title']}]({s['url']})**")
        lines.append(f"> {s['summary'][:700]}".strip())
        lines.append("")

    citations = [{"id": f"ref{i+1}", "title": r.get("title",""), "url": r.get("url","")}
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


# ---------- Day2: RAG ----------
from day2.instructor.rag_store import FaissStore
from day2.instructor.agents import answer_with_context  # non-stream

def run_rag(query: str, k: int = 5) -> Dict[str, Any]:
    index_dir = os.getenv("D2_INDEX_DIR", "data/processed/day2/faiss")
    store = FaissStore.load_or_new(index_dir=index_dir)

    ctx = store.search(query, k=k) if store.ntotal() > 0 else []
    answer = answer_with_context(query, ctx) if ctx else "_no local context_"

    citations = []
    for i, c in enumerate(ctx, 1):
        citations.append({
            "id": f"kb{i}",
            "title": c.get("title") or f"doc{i}",
            "url": c.get("url") or c.get("source") or ""
        })

    trace = {"ntotal": store.ntotal(), "module": "day2"}
    return {"answer_md": answer, "contexts": ctx, "citations": citations, "trace": trace}


# ---------- Day3: Government (NIPA) ----------
try:
    from day3.instructor.fetchers import fetch_nipa_list_by_query as fetch_nipa_list
except Exception:
    from day3.instructor.fetchers import fetch_nipa_list  # 표준명일 경우
from day3.instructor.normalize import normalize_items, deduplicate

# ranker가 없는 환경 대비 기본 랭커 제공(시그니처 호환)
try:
    from day3.instructor.ranker import rank_items as _rank_items
except Exception:
    def _rank_items(query, items, keywords=None, base_year=2025, **kwargs):
        keywords = keywords or []
        keys = list({*keywords, *re.findall(r"[가-힣A-Za-z0-9]{2,}", (query or "").lower())})
        out=[]
        for it in items:
            text=(it.get("title","")+" "+it.get("snippet","")).lower()
            s=sum(1 for k in keys if k and k in text)
            # 마감일 가까울수록 가중 (있으면)
            try:
                close = it.get("close_date") or ""
                # YYYY-MM-DD 형태만 간단 가중
                d = int(close.replace("-","")[:8]) if close else 0
                rec = 1.0 if d>0 else 0.2
            except Exception:
                rec = 0.2
            score = 0.7*(s/max(1,len(keys))) + 0.3*rec
            j=dict(it); j["score"]=score; out.append(j)
        out.sort(key=lambda x:x["score"], reverse=True)
        return out

def run_government(query: str, pages: int = 1, items: int = 10, base_year: int = 2025) -> Dict[str, Any]:
    raw = fetch_nipa_list(
        query=query,
        list_url=os.getenv("NIPA_LIST_URL","https://www.nipa.kr/home/2-2"),
        max_pages=pages,
        body_limit=int(os.getenv("NIPA_PER_ITEM_BYTES","900"))
    )
    pool = deduplicate(normalize_items(raw, "government"))
    ranked = _rank_items(query, pool, keywords=[], base_year=base_year)[:items]

    def _render_digest(lst: List[Dict]) -> str:
        text_items = [x for x in lst if x.get("content_type")=="text"]
        attach_items = [x for x in lst if x.get("content_type")=="attachment"]
        out = ["## Government Notice Digest", ""]
        if text_items:
            out.append("### 텍스트 중심 공고")
            for i, it in enumerate(text_items, 1):
                out.append(f"{i}. **[{it.get('title','')}]({it.get('url','')})**")
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
                out.append(f"{i}. **[{it.get('title','')}]({it.get('url','')})**")
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
    notices = [{
        "title": it.get("title"), "url": it.get("url"),
        "announce_date": it.get("announce_date"), "close_date": it.get("close_date"),
        "agency": it.get("agency"), "budget": it.get("budget"),
        "attachments": it.get("attachments", []), "content_type": it.get("content_type","text"),
        "score": it.get("score")
    } for it in ranked]
    trace = {"count": len(ranked), "module": "day3"}
    return {"digest_md": digest_md, "notices": notices, "trace": trace}


# ---------- 공통: 웹 결과 → RAG 컨텍스트 정규화 ----------
def normalize_to_rag_schema(web_results: list[dict]) -> list[dict]:
    """
    입력(엔진별 상이): title, url, snippet, content, site, domain, score, id
    출력: {id,title,url,source,summary,text,page,kind,score}
    """
    norm = []
    for r in web_results or []:
        title = (r.get("title") or "").strip()
        url = (r.get("url") or "").strip()
        site = r.get("site") or r.get("domain") or ""
        snippet = r.get("snippet") or r.get("summary") or ""
        content = r.get("content") or snippet
        score = float(r.get("score", 0.2))
        norm.append({
            "id": r.get("id") or url or title,
            "title": title, "url": url,
            "source": site, "summary": snippet, "text": content,
            "page": None, "kind": "web", "score": score,
        })
    return norm


# ---------- 주가 스냅샷(yfinance) ----------
def _guess_symbol(raw: str) -> Optional[str]:
    """
    문장 속에서 틱커/종목코드를 뽑아 yfinance용 심볼로 정규화.
    - 미국: 대문자 1~5자(예: AAPL, MSFT, TSLA)
    - 한국 6자리 숫자: 005930 -> 005930.KS (코스피), 035720 -> 035720.KQ(코스닥 추정은 생략, KS 기본)
    - 회사명 일부 매핑(간단): '삼성전자' -> 005930.KS
    """
    s = (raw or "").strip()

    # 1) 괄호/코드 패턴 우선: 005930, AAPL 등
    m = re.search(r"([A-Z]{1,5})(?![A-Z])", s)
    if m:
        return m.group(1)

    m = re.search(r"\b(\d{6})\b", s)
    if m:
        return f"{m.group(1)}.KS"

    # 2) 한글 회사명 간단 매핑
    name_map = {
        "삼성전자": "005930.KS",
        "카카오": "035720.KQ",
        "네이버": "035420.KS",
        "현대차": "005380.KS",
        "LG에너지솔루션": "373220.KS",
    }
    for k, v in name_map.items():
        if k in s:
            return v

    # 3) 공백 토큰에서 대문자 토큰 추출
    for tok in re.split(r"\s+", s):
        if re.fullmatch(r"[A-Z]{1,5}", tok):
            return tok

    return None

def get_stock_snapshot(query_or_symbol: str) -> Dict[str, Any]:
    """
    입력이 문장이어도 심볼을 추출, yfinance로 스냅샷(가급적 실시간에 가까운 정보) 반환.
    실패 시 {"error": "..."}.
    """
    try:
        import yfinance as yf
    except Exception as e:
        return {"error": f"yfinance import 실패: {e}"}

    sym = query_or_symbol.strip()
    # 심볼 추정
    if not re.fullmatch(r"[A-Z]{1,5}(\.[A-Z]{2})?|\d{6}\.K[SQ]", sym):
        g = _guess_symbol(sym)
        if not g:
            return {"error": f"심볼 추출 실패: '{query_or_symbol}'"}
        sym = g

    try:
        t = yf.Ticker(sym)
        info = t.fast_info if hasattr(t, "fast_info") else {}
        price = float(info.get("last_price") or info.get("last_trade") or 0.0)
        prev = float(info.get("previous_close") or 0.0)
        change = price - prev if (price and prev) else 0.0
        change_pct = (change/prev*100.0) if (price and prev) else 0.0

        mcap = info.get("market_cap")
        if mcap is not None:
            try:
                mcap = float(mcap)
            except Exception:
                mcap = None

        snap = {
            "symbol": sym,
            "price": price,
            "change": change,
            "change_pct": change_pct,
            "open": info.get("open"),
            "high": info.get("day_high") or info.get("high"),
            "low": info.get("day_low") or info.get("low"),
            "volume": info.get("volume"),
            "market_cap": mcap,
            "currency": info.get("currency") or ("KRW" if sym.endswith(".KS") or sym.endswith(".KQ") else "")
        }

        # 보조: 가격이 0이거나 None이면 과거 1일 데이터에서 보정 시도
        if not snap["price"] or math.isclose(snap["price"], 0.0):
            try:
                hist = t.history(period="1d", interval="1m")
                if not hist.empty:
                    snap["price"] = float(hist["Close"].iloc[-1])
            except Exception:
                pass

        if not snap["price"] or math.isclose(snap["price"], 0.0):
            return {"error": f"시세 조회 실패 또는 비거래: {sym}"}

        return snap

    except Exception as e:
        return {"error": f"yfinance 조회 실패: {e}"}

# === Compatibility wrapper for existing imports ===
def run_stock(query_or_symbol: str) -> dict:
    """
    Backward-compatible wrapper so callers importing `run_stock` keep working.
    Returns the same dict as `get_stock_snapshot(...)`.
    """
    return get_stock_snapshot(query_or_symbol)
