import os
import asyncio
from typing import Optional
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(), override=False)

from google.adk.agents import LlmAgent
from google.adk.runners import InMemoryRunner
from google.genai import types
from google.adk.models.lite_llm import LiteLlm

MODEL_NAME = os.getenv("MODEL_NAME", "openai/gpt-4o-mini")

# ---- URL 본문 요약 가이드 (Day1 자체 포함: day4에 의존 X) ----
URL_SUMMARY_GUIDE = """
역할: 웹페이지 본문을 사실 위주로 한국어 요약하는 에디터.
규칙:
1) 내비게이션/푸터/메뉴/개인정보 처리방침/스크립트/광고/공고 리스트 프레임 등은 모두 무시한다.
2) 본문 중심으로 핵심만 5~8문장에 담고, 불필요한 수식어/중복은 제거한다.
3) 날짜·기관·금액·기업명·제품명 등 구조화 가능한 팩트를 우선 포함한다.
4) 확실하지 않은 내용은 추정하지 말고, '자료 없음'으로 둔다.
출력: 평문 한국어 요약 1개 단락.
"""

# ---- 에이전트 정의 ----
summarizer_agent = LlmAgent(
    name="day1_url_summarizer",
    model=LiteLlm(model=MODEL_NAME) if "/" in MODEL_NAME else MODEL_NAME,
    instruction=URL_SUMMARY_GUIDE,
)

classifier_agent = LlmAgent(
    name="day1_topic_classifier",
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
        try:
            is_final = getattr(event, "is_final_response", lambda: False)()
            content = getattr(event, "content", None)
            if is_final and content and getattr(content, "parts", None):
                final_text = content.parts[0].text
        except Exception:
            continue
    return (final_text or "").strip()

def summarize_text(text: str) -> str:
    return asyncio.run(_run_once(summarizer_agent, text))

def classify_topic(text: str) -> str:
    label = (asyncio.run(_run_once(classifier_agent, text)) or "").strip()
    lab = label.lower()
    if any(k in lab for k in ["health", "의료", "병원", "제약"]):
        return "Healthcare"
    if any(k in lab for k in ["ict", "정보통신", "it", "소프트웨어", "클라우드", "ai"]):
        return "ICT"
    if any(k in lab for k in ["energy", "전력", "에너지", "배터리", "태양광", "풍력"]):
        return "Energy"
    return "Etc"
