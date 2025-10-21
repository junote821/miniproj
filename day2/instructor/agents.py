import os, asyncio
from typing import List, Dict
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(), override=False)

from google.adk.agents import LlmAgent
from google.adk.runners import InMemoryRunner
from google.genai import types
from google.adk.models.lite_llm import LiteLlm

MODEL_NAME = os.getenv("MODEL_NAME", "openai/gpt-4o-mini")

RAG_INST = """
당신은 근거 기반으로만 답하는 분석가입니다.
- 제공된 컨텍스트 외 추측 금지, 근거 없는 주장 금지
- 핵심만 간결하게 한국어로 작성
- 마지막에 인용을 최대 3개까지 [refN:제목|URL] 형식으로 첨부
"""

rag_agent = LlmAgent(
    name="rag_agent",
    model=LiteLlm(model=MODEL_NAME) if "/" in MODEL_NAME else MODEL_NAME,
    instruction=RAG_INST,
)

async def _run_once(agent: LlmAgent, text: str) -> str:
    runner = InMemoryRunner(agent=agent, app_name=agent.name)
    try:
        await runner.session_service.create_session(app_name=agent.name, user_id="u", session_id="s")
    except Exception:
        pass
    final = ""
    async for ev in runner.run_async(
        user_id="u",
        session_id="s",
        new_message=types.Content(role="user", parts=[types.Part(text=text)])
    ):
        if ev.is_final_response() and ev.content and ev.content.parts:
            final = ev.content.parts[0].text or ""
    return final.strip()

def answer_with_context(query: str, hits: List[Dict], k_refs: int = 3) -> str:
    # 컨텍스트 스니펫
    bullets = []
    for h in hits[:6]:
        title = h.get("title", "")
        snippet = h.get("summary") or (h.get("text", "")[:300])
        bullets.append(f"- {title}: {snippet}")
    # 인용
    refs = []
    for i, h in enumerate(hits[:k_refs], 1):
        refs.append(f"[ref{i}:{h.get('title','ref')}|{h.get('url','')}]")

    prompt = f"""질문: {query}

아래 컨텍스트를 바탕으로만 간결하게 답변하라(추측 금지).

컨텍스트:
{os.linesep.join(bullets)}

참고 인용:
{" ".join(refs)}
"""
    return asyncio.run(_run_once(rag_agent, prompt))
