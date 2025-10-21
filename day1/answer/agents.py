import os, asyncio
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(), override=False)

from google.adk.agents import LlmAgent
from google.adk.runners import InMemoryRunner
from google.genai import types
from google.adk.models.lite_llm import LiteLlm

MODEL_NAME = os.getenv("MODEL_NAME", "openai/gpt-4o-mini")

SUMMARIZER_INST = """
당신은 분석가입니다. 입력 텍스트를 정확히 5문장으로 한국어 요약하세요.
- 과장 금지, 사실 위주, 불확실한 부분은 표시
- 목록/표현 생략, 문장부호 정상 사용
"""
CLASSIFIER_INST = """
다음 텍스트의 도메인을 하나만 선택해 소문자로 출력하라: healthcare, ict, energy, etc
설명하지 말고 라벨만 출력.
"""

summarizer_agent = LlmAgent(name="summarizer_agent",
    model=LiteLlm(model=MODEL_NAME) if "/" in MODEL_NAME else MODEL_NAME,
    instruction=SUMMARIZER_INST)
classifier_agent = LlmAgent(name="classifier_agent",
    model=LiteLlm(model=MODEL_NAME) if "/" in MODEL_NAME else MODEL_NAME,
    instruction=CLASSIFIER_INST)

async def _run_once(agent: LlmAgent, text: str) -> str:
    runner = InMemoryRunner(agent=agent, app_name=agent.name)
    try:
        await runner.session_service.create_session(app_name=agent.name, user_id="u", session_id="s")
    except Exception:
        pass
    final = ""
    async for ev in runner.run_async(user_id="u", session_id="s",
        new_message=types.Content(role="user", parts=[types.Part(text=text)])):
        if ev.is_final_response() and ev.content and ev.content.parts:
            final = ev.content.parts[0].text or ""
    return final.strip()

def summarize_text(text: str) -> str:
    return asyncio.run(_run_once(summarizer_agent, text))

def classify_topic(text: str) -> str:
    lab = asyncio.run(_run_once(classifier_agent, text)).strip().lower()
    if any(k in text.lower() for k in ["medical","health","헬스","의료","바이오"]):
        return "healthcare"
    return lab if lab in {"healthcare","ict","energy","etc"} else "etc"
