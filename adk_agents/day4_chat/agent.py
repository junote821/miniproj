import os, time
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(), override=False)

from typing import Any, Dict
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools.agent_tool import AgentTool

from day4.instructor.main import run_router_app

MODEL_NAME = os.getenv("MODEL_NAME", "openai/gpt-4o-mini")

def orchestrate(query: str) -> str | Dict[str, Any]:
    md = run_router_app(query, debug=False)
    ts = time.strftime("%Y%m%d_%H%M%S")
    os.makedirs("data/processed", exist_ok=True)
    out_path = f"data/processed/day4_chat_{ts}.md"
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(md)
        md = md + f"\n\n---\nSaved to: `{out_path}`\n"
    except Exception:
        pass
    return md

def list_capabilities() -> str:
    return (
        "사용 가능한 도구:\n"
        "1) functions.orchestrate(query: str)  — Day4 파이프라인 실행, Markdown 생성 및 파일 저장\n"
        "2) functions.list_capabilities()     — 이 설명 표시\n"
    )

pipeline_agent = LlmAgent(
    name="day4_pipeline_agent",
    model=LiteLlm(model=MODEL_NAME),
    instruction=(
        "You are an orchestrator agent for Day4.\n"
        "- If user asks about tools/capabilities, call 'list_capabilities' and return as-is.\n"
        "- Otherwise ALWAYS call 'orchestrate' with the user's full message.\n"
        "- The tool returns final markdown. Return it verbatim."
    ),
    tools=[list_capabilities, orchestrate],
)

root_agent = LlmAgent(
    name="kt_aivle_day4_chat",
    model=LiteLlm(model=MODEL_NAME),
    instruction=(
        "You are the chat entry.\n"
        "- Delegate everything to the downstream agent and return exactly what it returns."
    ),
    tools=[AgentTool(agent=pipeline_agent)],
)
