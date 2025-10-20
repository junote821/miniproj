import os
import asyncio
from typing import Optional
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(), override=False)

from google.adk.agents import LlmAgent
from google.adk.runners import InMemoryRunner
from google.genai import types
from google.adk.models.lite_llm import LiteLlm

MODEL_NAME = os.getenv("MODEL_NAME", "openai/gpt-5")

# ---- 에이전트 정의 ----
summarizer_agent = LlmAgent(
    name="summarizer_agent",
    model=LiteLlm(model=MODEL_NAME) if "/" in MODEL_NAME else MODEL_NAME,
    instruction=(
        "역할: 보고서 편집자.\n"
        "규칙:\n"
        "1) 입력 내용을 한국어로 정확히 5문장으로 요약한다.\n"
        "2) 사실만 유지하고 추정은 금지한다.\n"
        "3) 불필요한 수식어/중복 표현을 제거한다.\n"
    ),
)

classifier_agent = LlmAgent(
    name="classifier_agent",
    model=LiteLlm(model=MODEL_NAME) if "/" in MODEL_NAME else MODEL_NAME,
    instruction=(
        "Classify the user's topic into one of {Healthcare, ICT, Energy, Etc}. "
        "Respond with the label only."
    ),
)

# ---- 공통 실행 헬퍼 (Runner로 1회 대화 실행) ----
async def _run_once(agent: LlmAgent, text: str) -> str:
    runner = InMemoryRunner(agent=agent, app_name=agent.name)
    session_service = runner.session_service

    user_id = "local_user"
    session_id = f"{agent.name}_session"

    # 세션이 이미 있으면 create가 실패할 수 있으므로 있어도 넘어가게 처리
    try:
        await session_service.create_session(
            app_name=agent.name, user_id=user_id, session_id=session_id
        )
    except Exception:
        pass

    final_text: Optional[str] = None
    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=types.Content(role="user", parts=[types.Part(text=text)]),
    ):
        if event.is_final_response() and event.content and event.content.parts:
            final_text = event.content.parts[0].text
    return (final_text or "").strip()

def summarize_text(text: str) -> str:
    return asyncio.run(_run_once(summarizer_agent, text))

def classify_topic(text: str) -> str:
    label = asyncio.run(_run_once(classifier_agent, text)).strip()
    lab = label.lower()
    if any(k in lab for k in ["health", "의료", "병원", "제약"]):
        return "Healthcare"
    if any(k in lab for k in ["ict", "정보통신", "it", "소프트웨어", "클라우드"]):
        return "ICT"
    if any(k in lab for k in ["energy", "전력", "에너지", "배터리", "태양광", "풍력"]):
        return "Energy"
    return "Etc" if label else "Etc"
