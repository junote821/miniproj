import os
import asyncio
from typing import List, Dict
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(), override=False)

from google.adk.agents import LlmAgent
from google.adk.runners import InMemoryRunner
from google.genai import types
from google.adk.models.lite_llm import LiteLlm

# ----- 모델/시스템 프롬프트 -----
MODEL_NAME = os.getenv("MODEL_NAME", "openai/gpt-4o-mini")

RAG_INST = """역할: 근거 기반 한국어 분석가.
규칙:
- 제공된 컨텍스트(아래 bullets)만 사용, 외부 지식/추정 금지.
- 사실/수치/정의는 원문 표현을 유지하고, 해석은 최소화.
- 답변은 한국어 한글 위주로 간결히.
- 끝에 참고 인용을 공백으로 나열: [ref1:제목|URL] [ref2:제목|URL]
- 컨텍스트가 부족하면 '해당 자료에서 확증 불가'를 분명히 표기.
출력: 단락형 한국어 답변 1~2개 + 인용 라인.
"""

rag_agent = LlmAgent(
    name="adk_day2_rag_agent",
    model=LiteLlm(model=MODEL_NAME) if "/" in MODEL_NAME else MODEL_NAME,
    instruction=RAG_INST,
)

# ----- 내부 실행 유틸(비동기) -----
async def _run_once(agent: LlmAgent, prompt: str) -> str:
    """ADK InMemoryRunner로 프롬프트 1회 실행하고 최종 텍스트를 반환."""
    app_name = agent.name
    runner = InMemoryRunner(agent=agent, app_name=app_name)

    try:
        await runner.session_service.create_session(
            app_name=app_name, user_id="instructor", session_id="sess1"
        )
    except Exception:
        pass

    content = types.Content(role="user", parts=[types.Part(text=prompt)])
    chunks: List[str] = []

    async for ev in runner.run_async(
        user_id="instructor", session_id="sess1", new_message=content
    ):
        try:
            if getattr(ev, "content", None) and ev.content.parts:
                for p in ev.content.parts:
                    if getattr(p, "text", None):
                        chunks.append(p.text)
        except Exception:
            continue

    out = ("".join(chunks)).strip()
    return out or "(no output)"

# ----- 공개 API -----
def answer_with_context(query: str, hits: List[Dict], k_refs: int = 3) -> str:
    """
    hits: rag_store.search() 표준 스키마
      {id,title,url,source,summary,text,page,kind,score}
    """
    if not hits:
        return "컨텍스트가 없어 답변을 생성할 수 없습니다. (로컬 문서 미탐색)"

    # 상위 6개를 불릿 컨텍스트로 구성
    bullets: List[str] = []
    for h in hits[:6]:
        title = h.get("title") or ""
        page = h.get("page")
        src = h.get("source") or ""
        txt = (h.get("text") or "").strip()
        head = f"- [{title}] p.{page} | {src}".strip(" |")
        body = (txt[:800] + ("…" if len(txt) > 800 else "")) if txt else ""
        bullets.append(f"{head}\n{body}")

    # 인용 3개
    refs: List[str] = []
    for i, h in enumerate(hits[:max(1, k_refs)], 1):
        refs.append(f"[ref{i}:{h.get('title','ref')}|{h.get('url','')}]")

    prompt = f"""질문: {query}

아래 컨텍스트만 근거로 간결하게 답하라(추측 금지).

컨텍스트:
{os.linesep.join(bullets)}

참고 인용:
{" ".join(refs)}
"""
    return asyncio.run(_run_once(rag_agent, prompt))
