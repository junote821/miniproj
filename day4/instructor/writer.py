import os, asyncio
from typing import Dict, Any
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import InMemoryRunner
from google.genai import types

MODEL_NAME = os.getenv("MODEL_NAME", "openai/gpt-4o-mini")

WRITER_INST = """
You are a senior analyst. Given (A) RAG snippets and/or (B) Web research summary,
compose a clean Korean markdown report with this structure:

- Executive Summary: 3~5 bullets
- Market Trends: bullets or short paragraphs
- Regulation & Policy (by region if possible): bullets
- Risks & Considerations: bullets
- Outlook / Recommendations: 3 bullets
- References: use the provided citation handles like [ref1], [kb1] etc.

Rules:
- No speculation beyond given inputs.
- Keep sentences concise and factual.
- Prefer Korean headings and bullets.
"""

async def _run_once(agent: LlmAgent, prompt: str) -> str:
    runner = InMemoryRunner(agent=agent, app_name=agent.name)
    try:
        await runner.session_service.create_session(app_name=agent.name, user_id="u", session_id="w")
    except Exception:
        pass
    out = ""
    async for ev in runner.run_async(
        user_id="u", session_id="w",
        new_message=types.Content(role="user", parts=[types.Part(text=prompt)])
    ):
        if ev.is_final_response() and ev.content and ev.content.parts:
            out = ev.content.parts[0].text or ""
    return out.strip() or "(no output)"

def _mk_refs(rag: Dict[str,Any] | None, research: Dict[str,Any] | None) -> str:
    refs=[]
    if rag:
        for i,c in enumerate(rag.get("citations") or [], 1):
            refs.append(f"[kb{i}] {c.get('title','')} — {c.get('url','')}")
    if research:
        for c in research.get("citations") or []:
            refs.append(f"[{c.get('id','ref?')}] {c.get('title','')} — {c.get('url','')}")
    return "\n".join(f"- {r}" for r in refs)

def _mk_context_blocks(rag: Dict[str,Any] | None) -> str:
    if not rag: return ""
    blocks=[]
    for h in (rag.get("contexts") or [])[:5]:
        t = h.get("title","")
        txt = (h.get("text") or h.get("summary") or "")[:800]
        src = h.get("source","")
        blocks.append(f"### {t}\n`{src}`\n> {txt}")
    return "\n\n".join(blocks)

def compose_report(query: str, rag: Dict[str,Any] | None, research: Dict[str,Any] | None) -> str:
    # ⚠️ 하이픈 금지 → 언더스코어 사용
    agent = LlmAgent(name="d4_writer", model=LiteLlm(model=MODEL_NAME), instruction=WRITER_INST.strip())
    rag_block = _mk_context_blocks(rag)
    web_block = (research or {}).get("report_md","")
    refs_block = _mk_refs(rag, research)
    prompt = f"""질문: {query}

(A) RAG Snippets:
{rag_block or "_none_"}

(B) Web Research Summary:
{web_block or "_none_"}

[Citations]
{refs_block or "_none_"}
"""
    return asyncio.run(_run_once(agent, prompt))
