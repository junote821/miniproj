import os, json, asyncio, re
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(), override=False)

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import InMemoryRunner
from google.genai import types

from day2.instructor.rag_store import FaissStore
from day2.instructor.agents import answer_with_context
from .prompts import ROUTER_INST

MODEL_NAME = os.getenv("MODEL_NAME", "openai/gpt-4o-mini")
INDEX_DIR  = os.getenv("D2_INDEX_DIR", "data/processed/day2/faiss")

MIN_TOP_SCORE = float(os.getenv("RAG_MIN_TOP_SCORE", "0.25"))
MIN_COVERED   = int(os.getenv("RAG_MIN_COVERED", "3"))

HINT_GOV = os.getenv("ROUTER_HINT_GOV", "0") == "1"  # 운영 토글(옵션)

# ----------------------------- 유틸 -----------------------------
def _quality_ok(hits: List[Dict], min_top: float = MIN_TOP_SCORE, min_cov: int = MIN_COVERED) -> bool:
    if not hits:
        return False
    top_ok = hits[0].get("score", 0.0) >= min_top
    covered = sum(1 for h in hits if h.get("score", 0.0) >= (min_top * 0.7))
    return top_ok and (covered >= min_cov)

def _looks_like_government(q: str) -> bool:
    """조사/띄어쓰기/어순 변화까지 허용한 정부 공고 의도 감지(항상 사용)."""
    q = (q or "").lower()
    return bool(re.search(r"(사업\s*공고|공고|입찰|모집|조달|공모|지원\s*사업)", q))

def _pre_hint_intent(query: str) -> Optional[str]:
    """ROUTER_HINT_GOV=1일 때만 사전 힌트로 우선 government를 돌려줌(선택)."""
    if not HINT_GOV:
        return None
    return "government" if _looks_like_government(query) else None

def _extract_json(text: str) -> Dict[str, Any]:
    if not text:
        return {}
    t = text.strip()
    m = re.search(r"```json\s*(\{.*?\})\s*```", t, re.S)
    if m: t = m.group(1)
    m = re.search(r"(\{.*\})", t, re.S)
    if m: t = m.group(1)
    try:
        return json.loads(t)
    except Exception:
        return {}

async def _ask_planner(query: str) -> str:
    agent = LlmAgent(
        name="router-planner",
        model=LiteLlm(model=MODEL_NAME) if "/" in MODEL_NAME else MODEL_NAME,
        instruction=ROUTER_INST.strip(),
    )
    runner = InMemoryRunner(agent=agent, app_name=agent.name)
    try:
        await runner.session_service.create_session(
            app_name=agent.name, user_id="u", session_id="plan"
        )
    except Exception:
        pass

    text = ""
    async for ev in runner.run_async(
        user_id="u", session_id="plan",
        new_message=types.Content(role="user", parts=[types.Part(text=query)])
    ):
        try:
            is_final = getattr(ev, "is_final_response", lambda: False)()
            content = getattr(ev, "content", None)
            if is_final and content and getattr(content, "parts", None):
                part0 = content.parts[0]
                if getattr(part0, "text", None):
                    text = part0.text or ""
        except Exception:
            continue
    return text

def _normalize_plan(obj: Any) -> Dict[str, Any]:
    if isinstance(obj, dict):
        if "plan" in obj:
            obj.setdefault("intent", "research")
            obj.setdefault("confidence", 0.7)
            obj.setdefault("reasons", [])
            return obj
        if "intent" in obj:
            obj.setdefault("plan", [])
            obj.setdefault("confidence", 0.6)
            obj.setdefault("reasons", [])
            return obj
    return {"intent": "research", "confidence": 0.5, "reasons": ["planner-fallback"], "plan": []}

# ----------------------------- Router 본체 -----------------------------
def route(query: str) -> dict:
    # 0) RAG-First
    store = FaissStore.load_or_new(INDEX_DIR)
    hits: List[Dict] = store.search(query, k=6) if store.ntotal() > 0 else []
    if _quality_ok(hits):
        answer = answer_with_context(query, hits, k_refs=3)
        return {
            "intent": "answer",
            "confidence": 0.9,
            "reasons": ["rag-first-ok"],
            "plan": [{"tool": "rag_answer", "params": {"k": 6, "k_refs": 3}}],
            "route": "RAG",
            "hits": hits,
            "answer": answer,
        }

    # 1) (옵션) 사전 힌트: 운영상 빠른 우회가 필요하면 사용
    intent_hint = _pre_hint_intent(query)
    if intent_hint == "government":
        return {
            "intent": "government",
            "confidence": 0.8,
            "reasons": ["pre-hint:government"],
            "plan": [
                {"tool": "day3.government", "params": {"pages": 1, "items": 10, "base_year": 2025}},
                {"tool": "day2.rag", "params": {"k": 5}},
            ],
            "route": "PLANNER_ONLY",
            "hits": hits,
        }

    # 2) 플래너 호출
    try:
        raw = asyncio.run(_ask_planner(query))
        obj = _normalize_plan(_extract_json(raw))
    except Exception:
        obj = _normalize_plan(None)

    # 3) (항상 적용) 의미 기반 정부 의도 감지 → 플랜에 government 주입
    try:
        has_gov = any((s.get("tool") or "").lower() in ("day3.government", "government") for s in obj.get("plan", []))
    except Exception:
        has_gov = False
    if _looks_like_government(query) and not has_gov:
        obj.setdefault("reasons", []).append("inject-government-by-intent")
        # government 스텝을 맨 앞에 추가, rag 보강을 뒤에 추가
        obj["plan"] = [
            {"tool": "day3.government", "params": {"pages": 1, "items": 10, "base_year": 2025}},
            {"tool": "day2.rag", "params": {"k": 5}},
        ] + (obj.get("plan") or [])
        obj["final_output"] = obj.get("final_output") or "government_proposal"

    # 4) 플랜 없으면 기본 웹 폴백
    if not obj.get("plan"):
        obj["plan"] = [
            {"tool": "web_search", "params": {"q": query, "k": 6}},
            {"tool": "writer_with_context", "params": {"style": "ko-concise-with-refs"}},
        ]
        obj["reasons"].append("web-fallback-default")

    # 라우팅 메타
    obj["route"] = "WEB_FALLBACK" if len(hits) == 0 else "PLANNER_ONLY"
    obj["hits"] = hits

    # 디버깅 가시성(원하면 주석 해제)
    # print(f"[Router:RAG] ntotal={store.ntotal()} hits={len(hits)} top={(hits[0]['score'] if hits else 0):.3f}")

    return obj
