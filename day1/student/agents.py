import os, asyncio
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(), override=False)

from google.adk.agents import LlmAgent
from google.adk.runners import InMemoryRunner
from google.genai import types
from google.adk.models.lite_llm import LiteLlm

MODEL_NAME = os.getenv("MODEL_NAME", "openai/gpt-4o-mini")

# TODO-1: 요약 에이전트 시스템 프롬프트 작성 (5문장 한국어 요약, 금지/허용 규칙 포함)
SUMMARIZER_INST = """
(여기에 5문장 요약 규칙을 한국어로 작성하세요)
"""

# TODO-2: 분류 에이전트 시스템 프롬프트 작성 (labels: healthcare, ict, energy, etc 중 1개만 반환)
CLASSIFIER_INST = """
(여기에 도메인 라벨 분류 규칙을 작성하세요)
"""

summarizer_agent = LlmAgent(
    name="summarizer_agent",
    model=LiteLlm(model=MODEL_NAME) if "/" in MODEL_NAME else MODEL_NAME,
    instruction=SUMMARIZER_INST
)
classifier_agent = LlmAgent(
    name="classifier_agent",
    model=LiteLlm(model=MODEL_NAME) if "/" in MODEL_NAME else MODEL_NAME,
    instruction=CLASSIFIER_INST
)

async def _run_once(agent: LlmAgent, text: str) -> str:
    # TODO-3: InMemoryRunner로 스트리밍 실행하고 최종 응답 파트의 텍스트를 반환
    raise NotImplementedError("TODO-3: _run_once 구현")

def summarize_text(text: str) -> str:
    # TODO-4: summarizer_agent에 text를 넣어 5문장 요약 문자열 반환
    raise NotImplementedError("TODO-4: summarize_text 구현")

def classify_topic(text: str) -> str:
    # TODO-5: classifier_agent에 text를 넣어 라벨(healthcare/ict/energy/etc) 반환 (+소문자/후처리)
    raise NotImplementedError("TODO-5: classify_topic 구현")
