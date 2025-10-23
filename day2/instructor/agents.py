import os, asyncio, threading, queue
from typing import List, Dict, Awaitable
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(), override=False)

from google.adk.agents import LlmAgent
from google.adk.runners import InMemoryRunner
from google.genai import types
from google.adk.models.lite_llm import LiteLlm

MODEL_NAME = os.getenv("MODEL_NAME", "openai/gpt-4o-mini")

RAG_INST = """당신은 근거 기반으로만 답하는 분석가입니다.
- 제공된 컨텍스트 외 추측 금지, 근거 없는 주장 금지
- 핵심만 간결하게 한국어로 작성
- 답변 끝에 참고 인용을 공백으로 구분하여 표기: [ref1:제목|URL] [ref2:제목|URL]
"""

rag_agent = LlmAgent(
    name="rag_agent",
    model=LiteLlm(model=MODEL_NAME),
    instruction=RAG_INST,
)

async def _run_once_async(agent: LlmAgent, prompt: str) -> str:
    """ADK Runner를 ASYNC로 한 번 실행하고 텍스트만 모아 반환."""
    runner = InMemoryRunner(agent=agent, app_name=agent.name)
    try:
        await runner.session_service.create_session(
            app_name=agent.name, user_id="instructor", session_id="sess1"
        )
    except Exception:
        pass

    content = types.Content(role="user", parts=[types.Part(text=prompt)])
    out_chunks: list[str] = []
    async for event in runner.run_async(
        user_id="instructor",
        session_id="sess1",
        new_message=content,
    ):
        if event and getattr(event, "content", None) and event.content.parts:
            for p in event.content.parts:
                if p and getattr(p, "text", None):
                    out_chunks.append(p.text)
    return "".join(out_chunks).strip()

def _run_blocking(coro: Awaitable[str]) -> str:
    """
    이벤트 루프 유무 관계없이 안전 실행:
    - 루프 없음: asyncio.run(coro)
    - 루프 있음: 별도 스레드에서 asyncio.run(coro)
    """
    try:
        asyncio.get_running_loop()
        in_loop = True
    except RuntimeError:
        in_loop = False

    if not in_loop:
        return asyncio.run(coro)

    q: "queue.Queue[str]" = queue.Queue(maxsize=1)

    def _worker():
        try:
            res = asyncio.run(coro)
        except Exception as e:
            res = f"(error) {e}"
        q.put(res)

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    t.join()
    return q.get()

def answer_with_context(query: str, hits: List[Dict], k_refs: int = 3) -> str:
    """
    hits: rag_store.search() 표준 스키마
      {id,title,url,source,summary,text,page,kind,score}
    """
    bullets = []
    for h in hits[:6]:
        title = h.get("title") or ""
        page = h.get("page")
        src = h.get("source") or ""
        txt = (h.get("text") or "").strip()
        head = f"- [{title}] p.{page} | {src}".strip(" |")
        body = (txt[:800] + ("…" if len(txt) > 800 else "")) if txt else ""
        bullets.append(f"{head}\n{body}")

    refs = []
    for i, h in enumerate(hits[:k_refs], 1):
        refs.append(f"[ref{i}:{h.get('title','ref')}|{h.get('url','')}]")

    prompt = f"""질문: {query}

아래 컨텍스트를 바탕으로만 간결하게 답변하라(추측 금지).

컨텍스트:
{os.linesep.join(bullets)}

참고 인용:
{" ".join(refs)}
"""
    return _run_blocking(_run_once_async(rag_agent, prompt)) or ""
