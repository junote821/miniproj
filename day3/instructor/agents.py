import os, asyncio
from typing import List, Dict
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(), override=False)

from google.adk.agents import LlmAgent
from google.adk.runners import InMemoryRunner
from google.genai import types
from google.adk.models.lite_llm import LiteLlm

MODEL_NAME = os.getenv("MODEL_NAME","openai/gpt-4o-mini")

INTENT_INST = (
    "Classify the user's query into one of intents: {general_qa, news, market, government}. "
    "Return exactly one token."
)

# 텍스트형 공고 요약(핵심 포인트 3~5개)
TEXT_SUM_INST = """
다음 공고 본문을 읽고 한국어로 핵심 포인트 3~5개 불릿으로 요약하라.
- 지원대상, 신청자격, 주요 내용, 지원규모/예산, 접수기간/마감 등 실무자가 필요한 정보 위주
- 과장 금지, 불명확하면 '공고문 확인 필요'로 표기
"""

intent_agent = LlmAgent(
    name="intent_agent",
    model=LiteLlm(model=MODEL_NAME) if "/" in MODEL_NAME else MODEL_NAME,
    instruction=INTENT_INST
)
text_summarizer = LlmAgent(
    name="text_summarizer",
    model=LiteLlm(model=MODEL_NAME) if "/" in MODEL_NAME else MODEL_NAME,
    instruction=TEXT_SUM_INST
)

async def _run_once(agent: LlmAgent, text:str)->str:
    runner = InMemoryRunner(agent=agent, app_name=agent.name)
    try:
        await runner.session_service.create_session(app_name=agent.name, user_id="u", session_id="s")
    except Exception:
        pass
    final=""
    async for ev in runner.run_async(user_id="u", session_id="s",
        new_message=types.Content(role="user", parts=[types.Part(text=text)])):
        if ev.is_final_response() and ev.content and ev.content.parts:
            final = ev.content.parts[0].text or ""
    return final.strip()

def classify_intent(query:str)->str:
    lab = asyncio.run(_run_once(intent_agent, query)).strip().lower()
    return lab if lab in {"general_qa","news","market","government"} else "government"

def summarize_text_points(text: str) -> str:
    if not text: return "- 공고문 확인 필요"
    return asyncio.run(_run_once(text_summarizer, text))

def render_digest(items: List[Dict], query_keywords: List[str]) -> str:
    """
    텍스트형: 본문 요약 + 첨부(있으면)
    첨부형: 첨부 링크 목록 위주 + (가능하면 summary 1~2줄)
    """
    lines=[]
    lines.append("## Government Notice Digest\n")

    def _kw_match_row(it: Dict) -> str:
        mf = it.get("matched_fields") or []
        return f"`{', '.join(mf)}`" if mf else ""

    # 텍스트형 먼저
    text_items = [x for x in items if x.get("content_type")=="text"]
    attach_items = [x for x in items if x.get("content_type")=="attachment"]

    if text_items:
        lines.append("### 텍스트 중심 공고")
        for i, it in enumerate(text_items, 1):
            lines.append(f"\n**{i}. [{it.get('title','')}]({it.get('url','')})**  {_kw_match_row(it)}")
            meta = []
            if it.get("announce_date"): meta.append(f"공고일: {it['announce_date']}")
            if it.get("close_date"): meta.append(f"마감일: {it['close_date']}")
            if it.get("agency"): meta.append(f"기관: {it['agency']}")
            if it.get("budget"): meta.append(f"예산: {it['budget']}")
            if meta: lines.append("- " + " / ".join(meta))

            # 본문 요약 불릿
            bullets = summarize_text_points(it.get("summary","") or it.get("text",""))
            lines.append(bullets)

            # 첨부
            atts = it.get("attachments") or []
            if atts:
                lines.append("- 첨부:")
                for a in atts[:5]:
                    lines.append(f"  - [{a.get('name','file')}]({a.get('url','')})")

    if attach_items:
        lines.append("\n### 첨부 중심 공고")
        for i, it in enumerate(attach_items, 1):
            lines.append(f"\n**{i}. [{it.get('title','')}]({it.get('url','')})**  {_kw_match_row(it)}")
            meta = []
            if it.get("announce_date"): meta.append(f"공고일: {it['announce_date']}")
            if it.get("close_date"): meta.append(f"마감일: {it['close_date']}")
            if it.get("agency"): meta.append(f"기관: {it['agency']}")
            if it.get("budget"): meta.append(f"예산: {it['budget']}")
            if meta: lines.append("- " + " / ".join(meta))

            # 첨부 위주 안내
            atts = it.get("attachments") or []
            if atts:
                lines.append("- 첨부(주요 공고문/양식):")
                for a in atts[:8]:
                    lines.append(f"  - [{a.get('name','file')}]({a.get('url','')})")
            # 요약이 있으면 한 줄
            if it.get("summary"):
                lines.append(f"- 요약: {it['summary'][:160]}…")

    if not text_items and not attach_items:
        lines.append("_해당 조건에 부합하는 공고가 없습니다._")

    # 키워드 힌트
    if query_keywords:
        lines.append("\n> 검색 키워드: " + ", ".join(query_keywords))

    return "\n".join(lines)
