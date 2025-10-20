import os, asyncio
from typing import Optional, List, Dict
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
        "규칙:\n"
        "- 주어진 '근거 컨텍스트'만으로 한국어로 답하라.\n"
        "- 문장 끝에 최대 3개의 근거를 [refN:제목|출처] 형식으로 인용한다.\n"
        "- 확실치 않은 수치는 '추정치'로 표기한다.\n"
        "- 마지막에 '한계와 다음 액션'을 2줄 이내로 제시한다.\n"
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

def _format_refs(chunks: List[Dict], k_refs: int = 3) -> str:
    refs = []
    for i, c in enumerate(chunks[:k_refs], 1):
        title = c.get("title") or c.get("source", "")[:40]
        src = c.get("source", "")
        refs.append(f"[ref{i}:{title}|{src}]")
    return " ".join(refs)

def answer_with_context(question: str, chunks: List[Dict], k_refs: int = 3) -> str:
    # 컨텍스트(상위 k_refs만 본문 포함)
    ctx_lines = []
    for i, c in enumerate(chunks[:k_refs], 1):
        title = c.get("title") or c.get("source", "")
        ctx_lines.append(f"[{i}] {title}\n{c['text']}\n")
    context = "\n".join(ctx_lines) if ctx_lines else "(no context)"
    sys_p = (
        "다음은 질문과 관련된 근거 컨텍스트다. 컨텍스트에 기반해 답하고, 문장 끝에 인용을 덧붙여라.\n"
        f"{context}\n"
    )
    user_p = (
        f"질문: {question}\n"
        "출력 형식 예시: 핵심 답변 문장 ... [ref1:제목|출처] [ref2:제목|출처]\n"
        "마지막 줄에 '한계와 다음 액션: ...'을 1~2문장으로 요약."
    )
    body = asyncio.run(_run_once(ragqa_agent, sys_p, user_p))
    # 안전망: 인용이 아예 없으면 최소 1개는 붙여줌
    if "[ref" not in body:
        body = body.strip() + " " + _format_refs(chunks, k_refs=k_refs)
    return body

def answer_with_context(question: str, chunks: List[Dict], k_refs: int = 3) -> str:
    # (기존 함수 그대로 두세요 — 배치/테스트용)
    ctx_lines = []
    for i, c in enumerate(chunks[:k_refs], 1):
        title = c.get("title") or c.get("source", "")
        ctx_lines.append(f"[{i}] {title}\n{c['text']}\n")
    context = "\n".join(ctx_lines) if ctx_lines else "(no context)"
    sys_p = (
        "다음은 질문과 관련된 근거 컨텍스트다. 컨텍스트에 기반해 답하고, 문장 끝에 인용을 덧붙여라.\n"
        f"{context}\n"
    )
    user_p = (
        f"질문: {question}\n"
        "출력 형식 예시: 핵심 답변 문장 ... [ref1:제목|출처] [ref2:제목|출처]\n"
        "마지막 줄에 '한계와 다음 액션: ...'을 1~2문장으로 요약."
    )
    body = asyncio.run(_run_once(ragqa_agent, sys_p, user_p))
    if "[ref" not in body:
        body = body.strip() + " " + _format_refs(chunks, k_refs=k_refs)
    return body

# 추가: 스트리밍 버전 (콘솔에 바로바로 출력)
async def _run_once_stream(agent: LlmAgent, sys_prompt: str, user_prompt: str):
    runner = InMemoryRunner(agent=agent, app_name=agent.name)
    try:
        await runner.session_service.create_session(app_name=agent.name, user_id="u", session_id="s")
    except Exception:
        pass
    accumulated = ""
    async for ev in runner.run_async(
        user_id="u", session_id="s",
        new_message=types.Content(role="user", parts=[types.Part(text=f"{sys_prompt}\n\n{user_prompt}")]),
    ):
        # 이벤트 타입별로 delta 텍스트가 있을 때 바로 출력
        # (SDK 버전에 따라 속성명이 다를 수 있어 try/except)
        try:
            if hasattr(ev, "delta") and ev.delta and ev.delta.parts and ev.delta.parts[0].text:
                chunk = ev.delta.parts[0].text
                accumulated += chunk
                print(chunk, end="", flush=True)  # 🔥 스트리밍 출력
        except Exception:
            pass

        if ev.is_final_response() and ev.content and ev.content.parts:
            final_text = ev.content.parts[0].text or ""
            # 최종 본문이 누적보다 긴 경우 보정
            if len(final_text) > len(accumulated):
                print(final_text[len(accumulated):], end="", flush=True)
            print()  # 줄바꿈
            return final_text.strip()
    return accumulated.strip()

def answer_with_context_stream(question: str, chunks: List[Dict], k_refs: int = 3) -> str:
    ctx_lines = []
    for i, c in enumerate(chunks[:k_refs], 1):
        title = c.get("title") or c.get("source", "")
        ctx_lines.append(f"[{i}] {title}\n{c['text']}\n")
    context = "\n".join(ctx_lines) if ctx_lines else "(no context)"
    sys_p = (
        "다음은 질문과 관련된 근거 컨텍스트다. 컨텍스트에 기반해 답하고, 문장 끝에 인용을 덧붙여라.\n"
        f"{context}\n"
    )
    user_p = (
        f"질문: {question}\n"
        "출력 형식 예시: 핵심 답변 문장 ... [ref1:제목|출처] [ref2:제목|출처]\n"
        "마지막 줄에 '한계와 다음 액션: ...'을 1~2문장으로 요약."
    )
    # 스트리밍 실행
    return asyncio.run(_run_once_stream(ragqa_agent, sys_p, user_p))
