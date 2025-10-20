# Day2 스캐폴딩
# 목적: Retrieval한 청크를 컨텍스트로 넣고 LlmAgent로 답변 생성(인용 포함)

import os, asyncio
from typing import List, Dict, Optional
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(), override=False)

from google.adk.agents import LlmAgent
from google.adk.runners import InMemoryRunner
from google.genai import types
from google.adk.models.lite_llm import LiteLlm

MODEL_NAME = os.getenv("MODEL_NAME", "openai/gpt-4o-mini")

ragqa_agent = LlmAgent(
    name="ragqa_agent",
    model=LiteLlm(model=MODEL_NAME) if "/" in MODEL_NAME else MODEL_NAME,
    instruction=(
        "역할: 리서치 분석가.\n"
        "- 주어진 '근거 컨텍스트'만으로 한국어로 답하라.\n"
        "- 문장 끝에 최대 3개의 근거를 [refN:제목|출처] 형식으로 인용한다.\n"
        "- 근거가 부족하면 '추가 근거 필요'라고 명시한다.\n"
    ),
)

async def _run_once(agent: LlmAgent, sys_prompt: str, user_prompt: str) -> str:
    runner = InMemoryRunner(agent=agent, app_name=agent.name)
    try:
        await runner.session_service.create_session(app_name=agent.name, user_id="u", session_id="s")
    except Exception:
        pass
    final = ""
    async for ev in runner.run_async(
        user_id="u", session_id="s",
        new_message=types.Content(role="user", parts=[types.Part(text=f"{sys_prompt}\n\n{user_prompt}")]),
    ):
        if ev.is_final_response() and ev.content and ev.content.parts:
            final = ev.content.parts[0].text or ""
    return final.strip()

# --- TODO[Step B4-1]: 컨텍스트 조립 + 호출 ---
def answer_with_context(question: str, chunks: List[Dict], k_refs: int = 3) -> str:
    """
    요구사항:
    - chunks 상위 k_refs 만큼 선택해 다음 포맷으로 컨텍스트 문자열 구성:
      [1] <title>\n<text>\n\n[2] <title>\n<text>\n ...
    - sys_prompt = '다음은 ... 컨텍스트다' + context
    - user_prompt = '질문: ...' + 인용 예시 안내
    - _run_once 호출, 인용이 하나도 없으면 최소 1개 ref를 덧붙여 반환
    """
    # 컨텍스트 조립
    ctx_lines = []
    for i, c in enumerate(chunks[:k_refs], 1):
        title = c.get("title") or c.get("source", "")
        ctx_lines.append(f"[{i}] {title}\n{c['text']}\n")
    context = "\n".join(ctx_lines) if ctx_lines else "(no context)"

    sys_p = f"다음은 질문과 관련된 근거 컨텍스트다.\n{context}\n"
    user_p = (
        f"질문: {question}\n"
        "출력 형식 예시: 핵심 답변 문장 ... [ref1:제목|출처] [ref2:제목|출처]"
    )

    body = asyncio.run(_run_once(ragqa_agent, sys_p, user_p))
    if "[ref" not in body and chunks:
        # 최소 1개 인용 보정
        t = chunks[0].get("title") or chunks[0].get("source", "")
        s = chunks[0].get("source", "")
        body = body.strip() + f" [ref1:{t}|{s}]"
    return body

# (선택 과제) 스트리밍 버전은 강사용 참고하여 직접 구현해도 좋음
