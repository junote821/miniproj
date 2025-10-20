# Day1 템플릿
# 역할:
#  - SummarizerAgent: 입력 텍스트를 5문장 핵심 요약
#  - ClassifierAgent: 입력 주제를 간단 도메인(Healthcare/ICT/Energy/Etc)으로 분류
#
# 아래는 "프롬프트/지시문"과 "입력/출력" 구조를 익히는 목적
# TODO 주석을 따라가며 프롬프트를 조정해 보세요.

from typing import List
from google.adk.agents import Agent
from google.genai.types import Part, UserContent
from google.adk.models.lite_llm import LiteLlm

# ---- SummarizerAgent ----
summarizer_agent = Agent(
    name="summarizer_agent",
    model=LiteLlm(model="openai/gpt-4o-mini"),  # TODO: 필요 시 .env MODEL_NAME 사용하도록 변경
    instruction=(
        "You are a concise editor. Summarize the given content into exactly 5 Korean sentences. "
        "Keep facts. Avoid hallucinations. Do not add sources not present in the input."
    ),
)

def summarize_text(text: str) -> str:
    """
    입력 텍스트 -> 5문장 요약
    ADK는 이벤트 파트를 통해 멀티모달 입력을 받습니다.
    여기서는 텍스트 파트만 전달합니다.
    """
    content = UserContent(parts=[Part.from_text(text)])
    result = summarizer_agent.run(content)
    # result.text 가 없을 수도 있어 .text 접근 전 기본값 처리
    return getattr(result, "text", "").strip()

# ---- ClassifierAgent ----
classifier_agent = Agent(
    name="classifier_agent",
    model=LiteLlm(model="openai/gpt-4o-mini"),
    instruction=(
        "Classify the user's topic into one of: Healthcare, ICT, Energy, Etc. "
        "Return only the label (one word). If unsure, return 'Etc'."
    ),
)

def classify_topic(text: str) -> str:
    """
    입력 텍스트 -> 간단 도메인 레이블
    """
    content = UserContent(parts=[Part.from_text(text)])
    result = classifier_agent.run(content)
    label = getattr(result, "text", "Etc").strip()
    # 안전하게 표준 라벨 집합으로 정규화
    label_up = label.lower()
    if "health" in label_up or "의료" in label_up:
        return "Healthcare"
    if "ict" in label_up or "it" in label_up or "정보통신" in label_up:
        return "ICT"
    if "energy" in label_up or "에너지" in label_up:
        return "Energy"
    return "Etc"
