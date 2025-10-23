# day4/instructor/formatter.py
import os
import re
from datetime import datetime
from typing import Dict, List, Optional

# ----------------------------- 공통 유틸 -----------------------------
def _iso(date_str: Optional[str]) -> str:
    """
    'YYYY-MM-DD'로 정규화 시도. 실패하면 원문 or '미표기' 유지.
    허용 예: '2025-10-23', '2025.10.23', '2025/10/23', '2025년 10월 23일'
    """
    if not date_str:
        return "미표기"
    s = str(date_str).strip()
    # 숫자 추출
    m = re.findall(r"(\d{4})[./\-\s년]?\s*(\d{1,2})[./\-\s월]?\s*(\d{1,2})", s)
    if m:
        y, mo, d = m[0]
        try:
            return datetime(int(y), int(mo), int(d)).strftime("%Y-%m-%d")
        except Exception:
            pass
    # 'YYYY-MM'만 있는 경우
    m = re.findall(r"(\d{4})[./\-\s년]?\s*(\d{1,2})", s)
    if m:
        y, mo = m[0]
        try:
            return f"{int(y):04d}-{int(mo):02d}-??"
        except Exception:
            pass
    return s  # 원문 유지

def _money(s: Optional[str]) -> str:
    """
    금액 문자열을 간단 포맷. 수치가 있으면 원문 유지 + 단위 보강, 없으면 '미표기'.
    예) '20억원', '2,000만원', '최대 3억', '3 billion KRW'
    """
    if not s:
        return "미표기"
    ss = str(s).strip()
    # 숫자 존재 확인
    if re.search(r"\d", ss):
        return ss
    return "미표기"

def _yn(val) -> str:
    return "Y" if val else "N"

def _link(title: str, url: Optional[str]) -> str:
    if url:
        return f"[{title}]({url})"
    return title or ""

def _render_ctx_table(ctxs: List[Dict], title="RAG Retrieval (Top-6)") -> str:
    lines = [f"### {title}", "| # | 제목 | 점수 | 출처 |", "|---:|---|---:|---|"]
    for i, h in enumerate(ctxs[:6], 1):
        lines.append(f"| {i} | {h.get('title','')} | {h.get('score',0):.3f} | `{h.get('source','')}` |")
    return "\n".join(lines)

def _render_citations(cites: List[Dict]) -> str:
    if not cites:
        return "_no citations_"
    out = ["## Citations"]
    for i, c in enumerate(cites, 1):
        t = c.get("title") or f"ref{i}"
        u = c.get("url") or ""
        out.append(f"- [ref{i}] {t} — {u}")
    return "\n".join(out)

# ----------------------------- RAG 전용 (rag-only) -----------------------------
def format_rag_only_output(query: str, rag: Dict) -> str:
    ctxs = rag.get("contexts") or []
    ans = rag.get("answer_md") or "_no answer_"
    parts = [
        f"# RAG-only Report",
        f"- Query: {query}",
        "",
        _render_ctx_table(ctxs, "RAG Retrieval (Top-6)"),
        "",
        "## Answer",
        ans,
    ]
    return "\n".join(parts)

# ----------------------------- Research 보고서 -----------------------------
def format_research_output(query: str, research: Dict | None, rag: Dict | None) -> str:
    """
    research: run_research() 결과(dict) 또는 None
      - "report_md": 요약 보고서
      - "rag_schema_contexts": [ {id,title,url,source,summary,text,page,kind,score}, ... ]
      - "citations": [{title,url}, ...]
    rag: run_rag() 결과(dict) 또는 None
      - "answer_md": 문자열
      - "contexts": 위와 동일 스키마
      - "citations": [{title,url}, ...]
    """
    # 1) RAG만 있는 경우 → rag-only
    if (not research) and rag:
        return format_rag_only_output(query, rag)

    # 2) research만 있거나, 둘 다 있는 경우: 간결한 합성 보고서
    parts = [f"# Final Report — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
             f"- Query: {query}",
             ""]
    if research:
        parts += [
            "## Executive Summary (Web)",
            research.get("report_md") or "_no web summary_",
            ""
        ]
    if rag:
        parts += [
            "## Internal Context (RAG)",
            _render_ctx_table(rag.get("contexts") or [], "RAG Retrieval (Top-6)"),
            "",
            "### RAG Answer",
            rag.get("answer_md") or "_no rag answer_",
            ""
        ]

    # 인용(웹 우선 + RAG 추가)
    cites = []
    if research and research.get("citations"):
        cites.extend(research.get("citations"))
    if rag and rag.get("citations"):
        cites.extend(rag.get("citations"))
    parts += [_render_citations(cites)]

    return "\n".join(parts)

# ----------------------------- Government 산출물 -----------------------------
def _render_notices_table(notices: List[Dict]) -> str:
    """
    notices 스키마(권장):
      title, url, agency, announce_date, close_date, budget, program_type,
      eligibility(list[str] or str), requirements(list[str] or str),
      attachments(list[{name,url}]), content_type (text/attachment), score
    """
    lines = [
        "## Notices Table",
        "",
        "| # | 제목 | 기관 | 공고일 | 마감일 | 금액 | 유형/분야 | 주요요구사항 | 첨부 | 링크 |",
        "|---:|---|---|---|---|---|---|---|---:|---|",
    ]
    for i, it in enumerate(notices, 1):
        title = it.get("title") or ""
        url = it.get("url") or ""
        agency = it.get("agency") or ""
        ann = _iso(it.get("announce_date"))
        clo = _iso(it.get("close_date"))
        bud = _money(it.get("budget"))
        ptype = it.get("program_type") or ""
        # requirements는 한 줄 요약(최대 2개 bullet 결합)
        req = it.get("requirements")
        if isinstance(req, list):
            req_line = " • ".join([str(x) for x in req[:2]])
        else:
            req_line = (str(req) if req else "")
        atts = it.get("attachments") or []
        has_att = _yn(bool(atts))
        link = _link("원문", url)

        lines.append(
            f"| {i} | {title} | {agency} | {ann} | {clo} | {bud} | {ptype} | {req_line} | {has_att} | {link} |"
        )
    return "\n".join(lines)

def _render_proposal_draft(notices: List[Dict], rag: Dict | None) -> str:
    """
    공고 기반 제안 초안 섹션. RAG가 있으면 내 자료에서 힌트(차별화/리스크 대응)를 끌어다 쓸 수 있음.
    여기서는 간단한 골격만 제공.
    """
    # 최근/점수 높은 1건을 대표로 삼아 예시 초안 작성
    lead = notices[0] if notices else {}
    lead_title = lead.get("title") or ""
    lead_agency = lead.get("agency") or ""
    lead_due = _iso(lead.get("close_date"))

    lines = [
        "## 제안 초안",
        f"- **대상 공고**: {lead_title} ({lead_agency}, 마감: {lead_due})" if lead_title else "- **대상 공고**: 미선정",
        "",
        "### 목표",
        "- 공고 목적과 연계된 핵심 성과지표(KPI) 달성",
        "",
        "### 가치제안",
        "- 사용자/기관 관점의 직접적 효익(비용절감, 생산성, 접근성 향상 등)",
        "",
        "### 범위(스코프)",
        "- 요구사항을 충족하는 최소기능(MVP) 범위 정의",
        "- 데이터 수집·정제·모델링·배포/운영 범위 명확화",
        "",
        "### 산출물",
        "- 기술문서, PoC 결과 보고서, 운영 매뉴얼, 교육자료",
        "",
        "### 일정(마일스톤)",
        "- 착수 → 분석/설계 → 개발/구축 → 검증/인수 → 종료",
        "",
        "### 리스크/대응",
        "- 데이터 품질/보안/윤리 = 표준 준수·무결성 점검·접근권한 관리",
        "- 일정 지연 = 단위 마일스톤 크리티컬 경로 관리",
        "",
        "### 차별화",
        "- 도메인 특화 데이터/평가 프로토콜",
        "- 기존 레퍼런스/성공사례 근거 제시",
    ]

    # RAG가 있으면 한두 줄 보강(선택)
    if rag and rag.get("answer_md"):
        lines += ["", "### 내부자료 인사이트(요약)", rag["answer_md"][:800]]

    return "\n".join(lines)

def format_government_output(query: str, gov: Dict, rag: Dict | None) -> str:
    """
    gov: run_government() 결과(dict)
      - "digest_md": (기존) 자유 텍스트 요약
      - "notices": List[notice dict]  ← 본 포맷터는 **이 필드**를 우선 사용
    rag: run_rag() 결과(dict) 또는 None
    """
    notices = gov.get("notices") or []
    # 중복 방지(제목+URL 기준)
    seen = set(); uniq = []
    for it in notices:
        key = (it.get("title") or "", it.get("url") or "")
        if key in seen: 
            continue
        seen.add(key); uniq.append(it)
    notices = uniq

    parts = [
        f"# Government Proposal — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"- Query: {query}",
        "",
        _render_notices_table(notices),
        "",
        _render_proposal_draft(notices, rag),
        "",
        "## Citations",
    ]

    # 인용: notices 우선, 없으면 digest에서 best-effort 추출
    cites = []
    for i, it in enumerate(notices, 1):
        cites.append({"title": it.get("title") or f"notice{i}", "url": it.get("url") or ""})
    if not cites and gov.get("digest_md"):
        # URL 탐색 (best effort)
        urls = list(set(re.findall(r"https?://\S+", gov["digest_md"])))
        for i, u in enumerate(urls[:10], 1):
            cites.append({"title": f"ref{i}", "url": u})

    parts.append(_render_citations(cites))

    # (선택) RAG 컨텍스트 요약 추가
    if rag and rag.get("contexts"):
        parts += ["", _render_ctx_table(rag["contexts"], "RAG Retrieval (Top-6)")]

    return "\n".join(parts)
