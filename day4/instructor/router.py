import os, json, asyncio, re
from typing import Dict, Any, List
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(), override=False)

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import InMemoryRunner
from google.genai import types

MODEL_NAME = os.getenv("MODEL_NAME", "openai/gpt-4o-mini")

# 금융 질의 감지: 주가/주식/가격/티커/기업정보/재무/시총/지표
FIN_PAT = re.compile(
    r"(주가|주식|가격|시세|티커|ticker|기업\s*정보|재무|재무제표|분기실적|연간실적|시총|per|pbr|eps|배당)",
    re.I,
)

# (옵션) LLM 기반 플래너를 계속 쓰고 싶다면 prompts.ROUTER_INST를 유지
try:
    from .prompts import ROUTER_INST
except Exception:
    ROUTER_INST = "You are a planner. Return JSON with keys: plan, final_output, reasons."

async def _ask_planner(query: str) -> str:
    agent = LlmAgent(
        name="router_planner",
        model=LiteLlm(model=MODEL_NAME),
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
        if ev.is_final_response() and ev.content and ev.content.parts:
            text = ev.content.parts[0].text or ""
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

def route(query: str) -> dict:
    q = (query or "").strip()

    # 1) 금융 질의는 강제 플랜: stock + research, RAG/정부 제외
    if FIN_PAT.search(q):
        return {
            "intent": "finance",
            "confidence": 0.95,
            "reasons": ["finance-intent: stock+web only"],
            "plan": [
                {"tool": "day1.stock", "params": {"q": q}},
                {"tool": "day1.research", "params": {"top_n": 5, "summarize_top": 2}},
            ],
            "final_output": "research_report",
            "route": "PLANNER_ONLY",
            "hits": [],
        }

    # 2) 나머지는 (선택) LLM 플래너 사용 → 없으면 간단 웹 폴백
    try:
        text = asyncio.run(_ask_planner(q))
        obj = _normalize_plan(json.loads(text))
    except Exception:
        obj = _normalize_plan(None)

    if not obj.get("plan"):
        obj["plan"] = [
            {"tool": "day1.research", "params": {"top_n": 5, "summarize_top": 2}}
        ]
        obj["reasons"].append("web-fallback-default")
    obj.setdefault("final_output", "research_report")
    obj["route"] = "PLANNER_ONLY"
    obj["hits"] = []
    return obj
