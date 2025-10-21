"""
오케스트레이션(진입점):
1) 사용자 질의에서 키워드 추출
2) 목록/상세 수집 → 정규화/중복 제거
3) 간단 랭킹(키워드 OR 점수 + 최근성 가점)
4) 텍스트형 vs 첨부형 Digest 생성
5) 스냅샷 저장(MD/JSON)

핵심 TODO:
- 키워드 추출 개선
- 키워드 점수 함수 개선(정규식 경계, 첨부 가중 등)
- 랭킹 가중치 조정
- Digest 렌더링 형식(표/불릿) 개선
"""

import os, json, re
from datetime import datetime
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(), override=False)

from day3.student.fetchers import fetch_nipa_list
from day3.student.normalize import normalize_items, deduplicate
from day3.student.agents import summarize_text_points

# ---------- 키워드 추출 ----------

STOP = set(["그리고","또는","또","및","관련","대한","에서","으로","하는","에","의","을","를","은","는","이","가",
            "좀","좀더","알려줘","보고서","리포트","분석","사업","공고","지원","프로그램","사업공고","찾아줘"])

def extract_keywords(q: str, top_n: int = 6):
    """TODO-A: 더 나은 토크나이저/불용어 목록으로 개선해 보세요."""
    toks = re.findall(r"[가-힣A-Za-z0-9]{2,}", (q or "").lower())
    toks = [t for t in toks if t not in STOP]
    seen=set(); out=[]
    for t in toks:
        if t in seen: continue
        seen.add(t); out.append(t)
        if len(out)>=top_n: break
    return out

def keyword_score(item, keywords):
    """키워드 OR 스코어(0~1). 제목/요약/첨부 파일명에 키워드가 나타나면 가산"""
    blob = f"{item.get('title','')} {item.get('summary','')}".lower()
    atts = " ".join([(a.get('name') or "") for a in (item.get('attachments') or [])]).lower()
    text = blob + " " + atts
    if not keywords: return 0.0
    s=0.0
    for k in keywords:
        # TODO-B: \b경계 사용 등으로 정밀도 향상 (현재는 단순 포함)
        if k in text:
            s += 1.0
    return min(1.0, s / max(1, len(keywords)))

def annotate_matches(items, keywords):
    """매칭 근거(어느 필드에서 매칭됐는지) 주석"""
    for it in items:
        mf=[]
        blob=f"{it.get('title','')} {it.get('summary','')}".lower()
        if any(k in blob for k in keywords):
            mf.append("title/summary")
        if any(k in (a.get('name','').lower()) for k in keywords for a in (it.get('attachments') or [])):
            mf.append("attachments.name")
        it["matched_fields"]=mf
    return items

# ---------- 렌더링 ----------

def render_table(items, title="TABLE"):
    lines=[f"### {title}", "| # | 제목 | 점수 | 출처 |", "|---:|---|---:|---|"]
    for i, it in enumerate(items, 1):
        lines.append(f"| {i} | [{it.get('title','')}]({it.get('url','')}) | {it.get('score',0):.3f} | `{it.get('source','')}` |")
    return "\n".join(lines)

def render_digest(items, q_keywords):
    """TODO-C: 표 + 불릿의 조합, 또는 카드형 등으로 UI를 바꿔보세요"""
    lines=[]
    lines.append("## Government Notice Digest\n")

    text_items=[x for x in items if x.get("content_type")=="text"]
    attach_items=[x for x in items if x.get("content_type")=="attachment"]

    if text_items:
        lines.append("### 텍스트 중심 공고")
        for i, it in enumerate(text_items, 1):
            # TODO-D: matched_fields 표시는 불필요하면 제거해도 됩니다.
            mf = "`" + ", ".join(it.get("matched_fields",[])) + "`" if it.get("matched_fields") else ""
            lines.append(f"\n**{i}. [{it.get('title','')}]({it.get('url','')})**  {mf}")
            meta=[]
            if it.get("announce_date"): meta.append(f"공고일: {it['announce_date']}")
            if it.get("close_date"): meta.append(f"마감일: {it['close_date']}")
            if it.get("agency"): meta.append(f"기관: {it['agency']}")
            if it.get("budget"): meta.append(f"예산: {it['budget']}")
            if meta: lines.append("- " + " / ".join(meta))
            bullets = summarize_text_points(it.get("summary",""))
            lines.append(bullets)
            atts = it.get("attachments") or []
            if atts:
                lines.append("- 첨부:")
                for a in atts[:5]:
                    lines.append(f"  - [{a.get('name','file')}]({a.get('url','')})")

    if attach_items:
        lines.append("\n### 첨부 중심 공고")
        for i, it in enumerate(attach_items, 1):
            mf = "`" + ", ".join(it.get("matched_fields",[])) + "`" if it.get("matched_fields") else ""
            lines.append(f"\n**{i}. [{it.get('title','')}]({it.get('url','')})**  {mf}")
            meta=[]
            if it.get("announce_date"): meta.append(f"공고일: {it['announce_date']}")
            if it.get("close_date"): meta.append(f"마감일: {it['close_date']}")
            if it.get("agency"): meta.append(f"기관: {it['agency']}")
            if it.get("budget"): meta.append(f"예산: {it['budget']}")
            if meta: lines.append("- " + " / ".join(meta))
            atts = it.get("attachments") or []
            if atts:
                lines.append("- 첨부(공고문/양식):")
                for a in atts[:8]:
                    lines.append(f"  - [{a.get('name','file')}]({a.get('url','')})")
            if it.get("summary"):
                lines.append(f"- 요약: {it['summary'][:160]}…")

    if not text_items and not attach_items:
        lines.append("_해당 조건에 부합하는 공고가 없습니다._")

    if q_keywords:
        lines.append("\n> 검색 키워드: " + ", ".join(q_keywords))
    return "\n".join(lines)

# ---------- 메인 ----------

def main():
    print("=== Day3 (Student) — NIPA Digest ===")
    query = os.getenv("D3_QUERY", "SaaS 해외 진출 지원 공고 찾아줘")
    q_keywords = extract_keywords(query)
    print("Query keywords:", q_keywords)

    # 1) 수집
    url = os.getenv("NIPA_LIST_URL", "https://www.nipa.kr/home/2-2")
    pages = int(os.getenv("NIPA_MAX_PAGES", "1"))
    items = fetch_nipa_list(url, max_pages=pages, body_limit=int(os.getenv("NIPA_PER_ITEM_BYTES","900")))
    print(f"[RUN] collected: {len(items)}")

    # 2) 정규화 + 중복 제거
    pool = deduplicate(normalize_items(items, "government"))

    # 3) 간단 랭킹 (키워드 OR + 최근성)
    ranked=[]
    for it in pool:
        ks = keyword_score(it, q_keywords)   # 0~1
        rec = 0.0
        if it.get("announce_date"):
            try:
                y=int(it["announce_date"][:4])
                base=int(os.getenv("NIPA_MIN_YEAR","2024"))
                rec = 0.3 if y>=base else 0.0
            except Exception:
                pass
        # TODO-E: 가중치 조정
        it["score"] = ks*0.7 + rec*0.3
        ranked.append(it)
    ranked.sort(key=lambda x: x["score"], reverse=True)
    ranked = annotate_matches(ranked, q_keywords)

    # 4) Digest 렌더링
    md = []
    md.append(f"# Day3 Snapshot — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    md.append(f"- Query: {query}")
    md.append(f"- NIPA_LIST_URL: {url}")
    md.append(f"- NIPA_MAX_PAGES: {pages}\n")
    md.append(render_table(ranked[:15], "Ranked Government Items (Top-15)"))
    md.append("\n## Digest\n")
    md.append(render_digest(ranked[:10], q_keywords))
    out = "\n".join(md)

    os.makedirs("data/processed", exist_ok=True)
    path = "data/processed/day3_snapshot_student.md"
    with open(path, "w", encoding="utf-8") as f:
        f.write(out)
    print(f"[Saved] {path}")

    # 5) JSON (라우터용)
    jpath = "data/processed/day3_notices_student.json"
    digest = [{
        "title": it.get("title"),
        "url": it.get("url"),
        "announce_date": it.get("announce_date"),
        "close_date": it.get("close_date"),
        "agency": it.get("agency"),
        "budget": it.get("budget"),
        "attachments": it.get("attachments", []),
        "requirements": it.get("requirements"),
        "matched_fields": it.get("matched_fields", []),
        "score": it.get("score"),
        "summary": it.get("summary"),
        "content_type": it.get("content_type","text"),
    } for it in ranked[:10]]
    with open(jpath, "w", encoding="utf-8") as jf:
        json.dump({"query": query, "generated_at": datetime.now().isoformat(), "notices": digest},
                  jf, ensure_ascii=False, indent=2)
    print(f"[Saved] {jpath}")

if __name__ == "__main__":
    main()
