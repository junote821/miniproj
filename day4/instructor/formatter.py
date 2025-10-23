import os
from datetime import datetime
from typing import Dict, Any, List

def _table(rows: List[Dict]) -> str:
    lines = ["| # | 제목 | 마감일 | 기관 | 예산 | 출처 |",
             "|---:|---|---:|---|---|---|"]
    for i, it in enumerate(rows or [], 1):
        lines.append(
            f"| {i} | [{it.get('title','')}]({it.get('url','')}) | {it.get('close_date','-')} | "
            f"{it.get('agency','-')} | {it.get('budget','-')} | `{it.get('source','')}` |"
        )
    return "\n".join(lines)

def format_research_output(query: str, research: Dict[str,Any] | None, rag: Dict[str,Any] | None) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"# Final Report — {now}", f"- Query: {query}", ""]
    if rag and rag.get("contexts"):
        lines.append("## Internal Knowledge (RAG)")
        lines.append("".join(["\n"] + [f"- {c.get('title','')}" for c in rag["contexts"][:5]]))
        lines.append("")
    if research:
        lines.append("## Research Summary")
        lines.append(research.get("report_md","_no report_"))
        if research.get("citations"):
            lines.append("\n## Citations")
            for c in research["citations"]:
                lines.append(f"- [{c['id']}] {c['title']} — {c['url']}")
    return "\n".join(lines).strip()

def format_government_output(query: str, gov: Dict[str,Any], rag: Dict[str,Any] | None = None) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    notices = gov.get("notices") or []
    lines = [f"# Final Report — {now}", f"- Query: {query}", ""]
    lines.append("## Notices (Top)")
    lines.append(_table(notices))
    lines.append("")
    lines.append("## Digest")
    lines.append(gov.get("digest_md","_no digest_"))
    if rag and rag.get("contexts"):
        lines.append("\n## Internal Addendum (RAG excerpts)")
        for c in rag["contexts"][:3]:
            title = c.get("title","")
            txt = (c.get("text") or "")[:400]
            lines.append(f"**{title}**\n> {txt}…")
    return "\n".join(lines).strip()
