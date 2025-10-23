import os
from typing import List, Dict

# 기본은 "파싱된 필드"로 실무용 요약문을 자동 생성 (LLM 비의존)
def render_digest(items: List[Dict], keywords: List[str]) -> str:
    lines=[]
    lines.append("## Government Notice Digest\n")

    def _line(it: Dict) -> List[str]:
        t = it.get("title","")
        u = it.get("url","")
        ann = it.get("announce_date") or "-"
        clo = it.get("close_date") or "-"
        ag  = it.get("agency") or "-"
        bdg = it.get("budget") or "-"
        req = it.get("requirements") or ""
        summary_line = f"- 요약: 대상/자격·주요내용·예산·기간 중심으로 확인 필요"
        # requirements에서 핵심 키워드 1줄만 추출
        if req:
            summary_line = f"- 요약: {req[:160]}…" if len(req) > 160 else f"- 요약: {req}"
        meta=[]
        meta.append(f"공고일: {ann}")
        meta.append(f"마감일: {clo}")
        if ag != "-": meta.append(f"기관: {ag}")
        if bdg != "-": meta.append(f"예산: {bdg}")
        return [
            f"**[{t}]({u})**",
            "- " + " / ".join(meta),
            summary_line
        ]

    # 텍스트형 우선, 첨부형 후순
    text_items = [x for x in items if x.get("content_type")=="text"]
    attach_items = [x for x in items if x.get("content_type")=="attachment"]

    if text_items:
        lines.append("### 텍스트 중심 공고")
        for i, it in enumerate(text_items, 1):
            lines.append(f"\n{i}. " + _line(it)[0])
            lines.append(_line(it)[1])
            lines.append(_line(it)[2])

    if attach_items:
        lines.append("\n### 첨부 중심 공고")
        for i, it in enumerate(attach_items, 1):
            lines.append(f"\n{i}. " + _line(it)[0])
            lines.append(_line(it)[1])
            atts = it.get("attachments") or []
            if atts:
                lines.append("- 첨부:")
                for a in atts[:8]:
                    lines.append(f"  - [{a.get('name','file')}]({a.get('url','')})")

    if not text_items and not attach_items:
        lines.append("_조건에 맞는 공고 없음_")

    if keywords:
        lines.append("\n> 검색 키워드: " + ", ".join(keywords))
    return "\n".join(lines)
