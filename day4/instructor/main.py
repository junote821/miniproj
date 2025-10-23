import os
import argparse
import time
from datetime import datetime
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(), override=False)

from day4.instructor.router import route
from day4.instructor.tools_bridge import run_research, run_rag, run_government
from day4.instructor.formatter import format_research_output, format_government_output

# ----------------------------- Tracer (스모크 가시성) -----------------------------
class Tracer:
    def __init__(self, enable=True):
        self.enable = enable
        self.t0 = time.perf_counter()

    def log(self, msg):
        if not self.enable: return
        t = time.perf_counter() - self.t0
        print(f"[{t:6.2f}s] {msg}")

# ----------------------------- 유틸 -----------------------------
def _save_md(md: str, out_path: str = "data/processed/day4_final_snapshot.md"):
    os.makedirs("data/processed", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"\n[Saved] {out_path}")

def _render_hits_table(items, title="RAG Retrieval"):
    lines = [f"### {title}", "| # | 제목 | 점수 | 출처 |", "|---:|---|---:|---|"]
    for i, it in enumerate(items or [], 1):
        lines.append(f"| {i} | {it.get('title','')} | {it.get('score',0):.3f} | `{it.get('source','')}` |")
    return "\n".join(lines)

def parse_args():
    p = argparse.ArgumentParser(description="Day4 Router App (simple)")
    p.add_argument("-q", "--query",
                   default=os.getenv("D4_QUERY", "헬스케어 AI 규제 최신 동향 요약해줘"),
                   help="사용자 질의 (CLI > ENV > 기본값)")
    p.add_argument("--debug", action="store_true", help="자세한 진행 로그 출력")
    return p.parse_args()

# ----------------------------- 메인 로직 -----------------------------
def run_router_app(query: str, debug: bool = False) -> str:
    tr = Tracer(enable=True)  # 항상 보이게. 너무 많다고 느껴지면 enable=debug 로 바꾸세요.
    tr.log("Router 호출")

    decision = route(query)
    route_tag = decision.get("route") or "(unknown)"
    intent = decision.get("intent", "research")
    conf = float(decision.get("confidence", 0.0))
    reasons = ", ".join(decision.get("reasons", []) or [])
    hits = decision.get("hits") or []
    top_score = hits[0]["score"] if hits else 0.0

    tr.log(f"Router 결과 → route={route_tag}, intent={intent}, conf={conf:.2f}, hits={len(hits)}, top={top_score:.3f}")
    if reasons: tr.log(f"reasons: {reasons}")

    # 1) RAG 즉답 경로면 바로 저장 후 종료
    if route_tag == "RAG" and decision.get("answer"):
        tr.log("RAG 즉답 선택 — 포맷/저장")
        md_parts = [
            f"# Day4 Snapshot — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"- Query: {query}",
            _render_hits_table(hits, "RAG Retrieval (Top-6)"),
            "## Final Answer",
            decision["answer"]
        ]
        md = "\n\n".join(md_parts)
        _save_md(md)
        return md

    # 2) 플랜 실행 (매핑 단순화)
    steps = decision.get("plan") or []
    if steps:
        tr.log(f"플랜 실행 시작: {steps}")
    else:
        tr.log("플랜 없음 → 기본 intent 라우팅으로 전환")

    results = {}
    use_guard = os.getenv("GOV_GUARD", "0") == "1"  # 기본 OFF

    def exec_step(tool: str, params: dict):
        tool_l = (tool or "").lower()
        if tool_l in ("day1.research", "web_search", "research"):
            tr.log("run_research 실행")
            return ("research", run_research(
                query,
                top_n=int(params.get("top_n", os.getenv("D1_TOPN","5"))),
                summarize_top=int(params.get("summarize_top", os.getenv("D1_SUMM_TOP","2")))
            ))
        if tool_l in ("day2.rag", "rag", "knowledge_base", "kb"):
            tr.log("run_rag 실행")
            return ("rag", run_rag(query, k=int(params.get("k", 5))))
        if tool_l in ("day3.government", "government"):
            if use_guard:
                # 필요 시 간단 가드 (키워드/신뢰도 기반) — 기본은 비활성
                gov_keys = [k.strip() for k in os.getenv(
                    "GOV_KEYWORDS",
                    "사업공고,공고,입찰,모집,조달,공모,NIPA,정부과제"
                ).split(",") if k.strip()]
                if not any(k.lower() in (query or "").lower() for k in gov_keys):
                    tr.log("government 가드 차단(키워드 미포함) → skip")
                    return (None, None)
            tr.log("run_government 실행")
            return ("government", run_government(
                query,
                pages=int(params.get("pages", os.getenv("NIPA_MAX_PAGES","1"))),
                items=int(params.get("items", os.getenv("D3_ITEMS","10"))),
                base_year=int(params.get("base_year", os.getenv("NIPA_MIN_YEAR","2025")))
            ))
        if tool_l in ("writer_with_context", "writer"):
            tr.log("writer 플래그 on (포맷 단계에서 처리)")
            return ("writer", True)
        tr.log(f"알 수 없는 tool 스킵: {tool}")
        return (None, None)

    # 플랜 있으면 실행, 없으면 intent 기본 처리
    if steps:
        for s in steps:
            k, v = exec_step(s.get("tool"), s.get("params") or {})
            if k: results[k] = v
    else:
        if intent in ("knowledge_base", "rag"):
            tr.log("intent=KB → RAG 우선")
            results["rag"] = run_rag(query, k=5)
        elif intent == "government":
            tr.log("intent=government → Day3 실행")
            results["government"] = run_government(query)
        else:
            tr.log("intent=research → Day1 실행")
            results["research"] = run_research(query)

    # 3) 최종 포맷팅
    final_output = decision.get("final_output") or ("government_proposal" if "government" in results else "research_report")
    tr.log(f"포맷팅: {final_output}")

    if final_output == "government_proposal":
        md = format_government_output(
            query,
            gov=results.get("government") or {"digest_md": "_no government results_", "notices": [], "trace": {}},
            rag=results.get("rag")
        )
    else:
        md = format_research_output(
            query,
            research=results.get("research"),
            rag=results.get("rag")
        )

    _save_md(md)
    return md

def main():
    args = parse_args()
    print("=== Day4 (Instructor) — Simple Router Smoke ===")
    out = run_router_app(args.query, debug=args.debug)
    print("\n" + "="*60 + "\n")
    print(out)

if __name__ == "__main__":
    main()
