"""
역할: LLM을 사용해 텍스트형 공고를 짧은 불릿으로 요약
TODO 포인트:
- 요약 규칙(instruction) 튜닝
- (선택) 영어/숫자 섞인 공고 처리 스타일 추가
"""

import os, asyncio
from typing import List, Dict
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(), override=False)

from google.adk.agents import LlmAgent
from google.adk.runners import InMemoryRunner
from google.genai import types
from google.adk.models.lite_llm import LiteLlm

MODEL_NAME = os.getenv("MODEL_NAME","openai/gpt-4o-mini")

# TODO-3: 요약 규칙을 조정해보세요(불릿 개수, 형식, 금지 사항 등)
TEXT_SUM_INST = """
다음 공고 본문을 읽고 한국어로 핵심 포인트 3~5개 불릿으로 요약하라.
- 지원대상, 신청자격, 주요 내용, 지원규모/예산, 접수기간/마감을 우선
- 과장 금지, 불명확하면 '공고문 확인 필요'로 표기
"""

text_summarizer = LlmAgent(
    name="text_summarizer",
    model=LiteLlm(model=MODEL_NAME) if "/" in MODEL_NAME else MODEL_NAME,
    instruction=TEXT_SUM_INST
)

async def _run_once(agent: LlmAgent, text:str)->str:
    """하나의 프롬프트를 실행하고 최종 텍스트만 반환."""
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

def summarize_text_points(text: str) -> str:
    """TODO-4: 요약 길이/스타일을 바꾸고 결과가 어떻게 달라지는지 실험해보세요."""
    if not text:
        return "- 공고문 확인 필요"
    return asyncio.run(_run_once(text_summarizer, text))
