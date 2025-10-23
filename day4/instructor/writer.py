# day4/instructor/writer.py
import os
from typing import Dict, Any, List
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(), override=False)

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import InMemoryRunner
from google.genai import types

MODEL_NAME = os.getenv("MODEL_NAME", "openai/gpt-4o-mini")

WRITER_INST = """
역할: 주어진 자료(RAG 컨텍스트, 웹 요약, (선택) 주가 스냅샷)를 바탕으로만 보고서를 작성한다.

언어 규칙(매우 중요):
- **출력은 무조건 한국어로 작성**한다.
- 영어 문장/용어가 자료에 포함되어 있어도, 보고서 본문은 한국어로 자연스럽게 기술한다(고유명사·브랜드·티커 등은 원문 유지 가능).
- 한국어가 아닌 문장이 섞이면, 최종 출력 전에 한국어로 정돈한다.

사실성/범위 규칙:
- **추측 금지**. 제공된 자료 외 확언 금지.
- 자료에 없으면 “자료에 없음/불충분”으로 명시.
- 숫자/지표는 자료에서 확인된 값만 사용.
- 표/불릿은 과장 없이 간결하게.

출력 포맷(마크다운):
## Executive Summary (3~5 bullets)
## Ticker Snapshot (선택: 주가 스냅샷이 전달된 경우 표로 표시)
## Market/Topic Trends
## Regulation & Policy
## Risks & Considerations
## Outlook / Recommendations
## References (각 항목은 '제목 — URL' 형식)
"""

def _fmt_num(x):
    try:
        return f"{float(x):,.2f}"
    except Exception:
        return str(x)

def _render_stock(s:Dict[str,Any]|None)->str:
    if not s:
        return "_티커 스냅샷: 입력 없음_"
    if s.get("error"):
        return f"_티커 스냅샷 로드 실패: {s['error']}_"
    ch=f"{s.get('change',0.0):+.2f} ({s.get('change_pct',0.0):+.2f}%)"
    return (
        f"| 항목 | 값 |\n|---|---|\n"
        f"| 심볼 | `{s.get('symbol')}` |\n"
        f"| 가격 | {_fmt_num(s.get('price'))} {s.get('currency','')} |\n"
        f"| 전일대비 | {ch} |\n"
        f"| 시가/고가/저가 | {_fmt_num(s.get('open'))} / {_fmt_num(s.get('high'))} / {_fmt_num(s.get('low'))} |\n"
        f"| 거래량 | {s.get('volume')} |\n"
        f"| 시가총액 | {_fmt_num(s.get('market_cap'))} |\n"
    )

def _mk_refs(rag:Dict[str,Any]|None, research:Dict[str,Any]|None)->List[str]:
    refs=[]
    if research and research.get("citations"):
        for c in research["citations"]:
            t=(c.get("title") or "").strip() or c.get("id","ref")
            u=c.get("url") or ""
            refs.append(f"- {t} — {u}".strip())
    if rag and rag.get("citations"):
        for c in rag["citations"]:
            t=(c.get("title") or "").strip() or c.get("id","kb")
            u=c.get("url") or ""
            refs.append(f"- {t} — {u}".strip())
    return refs or ["- (no references)"]

def _run_once_sync(agent: LlmAgent, prompt: str) -> str:
    """
    ADK Web의 이벤트 루프 내부에서도 안전하게 동작하는 동기 실행 버전.
    """
    app_name = "d4_writer_app"
    runner = InMemoryRunner(agent=agent, app_name=app_name)
    try:
        runner.session_service.create_session_sync(
            app_name=app_name, user_id="u", session_id="w"
        )
    except Exception:
        pass

    out_chunks=[]
    for ev in runner.run(
        user_id="u", session_id="w",
        new_message=types.Content(role="user", parts=[types.Part(text=prompt)])
    ):
        if ev and getattr(ev, "content", None) and ev.content.parts:
            for p in ev.content.parts:
                if getattr(p, "text", None):
                    out_chunks.append(p.text)
    return "".join(out_chunks).strip() or "(no output)"

def compose_report(query: str,
                   rag: Dict[str,Any] | None,
                   research: Dict[str,Any] | None,
                   stock: Dict[str,Any] | None) -> str:
    # 참고문헌
    refs = "\n".join(_mk_refs(rag, research))

    # 컨텍스트(요약형)
    ctx_blks=[]
    if research and research.get("report_md"):
        ctx_blks.append(f"[WEB]\n{research['report_md']}")
    if rag and rag.get("contexts"):
        tops=[]
        for c in rag["contexts"][:6]:
            summ = (c.get('summary') or c.get('text',''))[:200]
            tops.append(f"- {c.get('title','')}: {summ}")
        ctx_blks.append("[RAG]\n" + "\n".join(tops))

    stock_blk = _render_stock(stock)

    # 한국어 고정 가드 포함
    prompt = f"""[지시]
다음 규칙을 엄격히 준수해 보고서를 작성하라.
- **출력은 반드시 한국어**로 작성한다(영어 문장/문구 섞지 않음. 고유명사는 원문 유지 가능).
- 제공 자료 외 **추측 금지**. 불충분하면 '자료 부족/불충분'으로 명시.
- 아래 '출력 포맷' 섹션을 그대로 따른다.

[사용자 질의]
{query}

[자료]
{os.linesep.join(ctx_blks) if ctx_blks else "(no context)"}

[티커 스냅샷]
{stock_blk}

[출력 포맷]
{WRITER_INST}

[참고문헌]
{refs}
"""

    agent = LlmAgent(
        name="d4_writer",
        model=LiteLlm(model=MODEL_NAME),
        instruction=WRITER_INST.strip()
    )
    return _run_once_sync(agent, prompt)
