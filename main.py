import os
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(), override=False)

from typing import Any, Dict
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools.agent_tool import AgentTool

# Day4 오케스트레이션 진입점 재사용
from day4.instructor.main import run_router_app

MODEL_NAME = os.getenv("MODEL_NAME", "openai/gpt-4o-mini")

def orchestrate(query: str) -> str | Dict[str, Any]:
    """
    Day4 파이프라인을 호출해 최종 Markdown을 반환합니다.
    - Input:
        query (str): 사용자 자연어 질의
    - Return:
        str (markdown) 또는 dict(ADK가 자동 포장)
    """
    # debug=False 로 UI 응답을 깔끔하게
    return run_router_app(query, debug=False)

# 하위(파이프라인) 에이전트: Function Tool 자동 래핑(도큐 기준)
# - tools 리스트에 파이썬 함수를 그대로 넣으면 ADK가 FunctionTool로 감쌈
#   (https://google.github.io/adk-docs/tools/function-tools/ 참고)

pipeline_agent = LlmAgent(
    name="day4_pipeline_agent",          # 하이픈 금지: 식별자 규칙 준수
    model=LiteLlm(model=MODEL_NAME),
    instruction=(
        "You are an orchestrator agent.\n"
        "- Always call the 'orchestrate' tool with the user's full message.\n"
        "- Return the tool's markdown output as-is."
    ),
    tools=[orchestrate],
)

# 루트(챗 UI 노출) 에이전트: Agent-as-a-Tool로 하위 에이전트를 도구처럼 사용
# - skip_summarization=True 로 하위 응답을 그대로 노출
agent = LlmAgent(
    name="kt_aivle_day4_chat",
    model=LiteLlm(model=MODEL_NAME),
    instruction=(
        "You are a chat entry.\n"
        "- Always call the 'pipeline' tool with the user's message.\n"
        "- Do NOT add extra commentary; just return the tool's output."
    ),
    tools=[AgentTool(agent=pipeline_agent, skip_summarization=True)],
)

if __name__ == "__main__":
    # CLI 단독 확인
    q = os.getenv("D4_QUERY", "최신 헬스케어 시장 동향과 규제를 알려줘")
    print(orchestrate(q))
