import os, json, re, asyncio
from typing import Any, Dict, List
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(), override=False)

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import InMemoryRunner
from google.genai import types

# Day2: quick RAG signal
from day2.instructor.rag_store import FaissStore
from day2.instructor.agents import answer_with_context

from day4.instructor.prompts import ROUTER_INST

MODEL_NAME = os.getenv("MODEL_NAME", "openai/gpt-4o-mini")
INDEX_DIR  = os.getenv("D2_INDEX_DIR", "data/processed/day2/faiss")

GOV_WORDS = ["사업공고","공고","입찰","모집","조달","공모","NIPA","정부과제"]

# ROUTER_INST = """
# You are a planner. Decide a minimal tool plan given the query.
# Tools:
# - day1.research {top_n,summarize_top}
# - day2.rag {k}
# - day3.government {pages,items,base_year}

# Rules:
# - If query contains gov keywords, include day3.government first. Optionally add day2.rag.
# - Else try day2.rag first; if likely insufficient, add day1.research.
# Output JSON only:
# {"plan":[{"tool":"...","params":{...}},...], "final_output":"research_report|government_proposal","reasons":["..."]}
# """

def _has_gov_kw(q: str) -> bool:
    ql = (q or "").lower()
    return any(k.lower() in ql for k in GOV_WORDS)

def _rag_ok(query: str, min_top: float = 0.25, min_cov: int = 3) -> tuple[bool, list[dict], float]:
    store = FaissStore.load_or_new(INDEX_DIR)
    if store.ntotal() <= 0:
        return False, [], 0.0
    hits = store.search(query, k=6)
    top = hits[0]["score"] if hits else 0.0
    cov = sum(1 for h in hits if h.get("score",0) >= (min_top*0.7))
    return (top >= min_top and cov >= min_cov), hits, top

async def _ask_planner(query: str) -> str:
    agent = LlmAgent(
        name="d4_router",
        model=LiteLlm(model=MODEL_NAME),
        instruction=ROUTER_INST.strip(),
    )
    runner = InMemoryRunner(agent=agent, app_name=agent.name)
    try:
        await runner.session_service.create_session(app_name=agent.name, user_id="u", session_id="s")
    except Exception:
        pass
    out = ""
    async for ev in runner.run_async(
        user_id="u", session_id="s",
        new_message=types.Content(role="user", parts=[types.Part(text=query)])
    ):
        if ev.is_final_response() and ev.content and ev.content.parts:
            out = ev.content.parts[0].text or ""
    return out


RECENT_TOKENS = ["최신","최근","요즘","올해","분기","이번달","이번 달","지난달","업데이트","업데이트된"]

def _has_recent(q: str) -> bool:
    ql = (q or "").lower()
    return any(tok.lower() in ql for tok in RECENT_TOKENS)

def route(query: str) -> Dict[str, Any]:
    # 정부 키워드 힌트는 그대로
    if _has_gov_kw(query):
        plan = [
            {"tool":"day3.government","params":{"pages":int(os.getenv("NIPA_MAX_PAGES","1")),"items":10,"base_year":int(os.getenv("NIPA_MIN_YEAR","2025"))}},
            {"tool":"day2.rag","params":{"k":5}}
        ]
        return {"intent":"government","confidence":0.85,"reasons":["gov-keyword"],"plan":plan,"route":"PLANNER_ONLY","hits":[]}

    # RAG-first quick check
    ok, hits, top = _rag_ok(query)

    # [NEW] 최신성 포함 시엔 RAG 즉답 금지 → 하이브리드 플랜으로 유도
    if ok and not _has_recent(query):
        ans = answer_with_context(query, hits, k_refs=3)
        return {
            "intent":"answer","confidence":0.9,"reasons":["rag-first-ok"],
            "plan":[{"tool":"day2.rag","params":{"k":6}}],
            "route":"RAG","hits":hits,"answer":ans,"top":top
        }

    # fallback / 혹은 최신성 → 하이브리드 기본 플랜
    try:
        obj = json.loads(asyncio.run(_ask_planner(query)))
    except Exception:
        obj = {}
    if not isinstance(obj, dict) or "plan" not in obj:
        obj = {
            "plan":[
                {"tool":"day2.rag","params":{"k":5}},
                {"tool":"day1.research","params":{"top_n":5,"summarize_top":2}}
            ],
            "final_output":"research_report",
            "reasons":["fallback-minimal" + ("-recent" if _has_recent(query) else "")]
        }
    obj.setdefault("final_output","research_report")
    obj.setdefault("reasons",[])
    obj["route"]="PLANNER_ONLY"; obj["hits"]=hits; obj["top"]=top
    return obj
