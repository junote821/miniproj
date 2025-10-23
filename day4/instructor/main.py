import os, argparse, time
from datetime import datetime
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(), override=False)

from day4.instructor.router import route
from day4.instructor.tools_bridge import run_research, run_rag, run_government, run_stock
from day4.instructor.formatter import format_research_output, format_government_output
from day4.instructor.writer import compose_report

def _save_md(md: str, out_path: str = "data/processed/day4_final_snapshot.md"):
    os.makedirs("data/processed", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"[Saved] {out_path}")

def run_router_app(query: str, debug: bool = True) -> str:
    t0 = time.time()
    if debug: print("=== Day4 (Instructor) — Simple Router Smoke ===")
    if debug: print(f"[{time.time()-t0:6.2f}s] Router 호출")
    decision = route(query)
    if debug:
        print(f"[{time.time()-t0:6.2f}s] Router 결과 → route={decision.get('route')}, "
              f"intent={decision.get('intent','research')}, conf={decision.get('confidence',0.0):.2f}, "
              f"hits={len(decision.get('hits') or [])}, top={decision.get('top',0):.3f}")
        if decision.get("reasons"):
            print(f"[{time.time()-t0:6.2f}s] reasons: {', '.join(decision['reasons'])}")

    # 플랜 실행
    steps = decision.get("plan") or []
    if debug and steps:
        print(f"[{time.time()-t0:6.2f}s] 플랜 실행 시작: {steps}")

    results = {"rag": None, "research": None, "government": None, "stock": None}

    def exec_step(tool: str, params: dict):
        if tool == "day2.rag":
            if debug: print(f"[{time.time()-t0:6.2f}s] run_rag 실행")
            return ("rag", run_rag(query, k=int(params.get("k", 5))))
        if tool == "day1.research":
            if debug: print(f"[{time.time()-t0:6.2f}s] run_research 실행")
            return ("research", run_research(
                query,
                top_n=int(params.get("top_n", 5)),
                summarize_top=int(params.get("summarize_top", 2)),
            ))
        if tool == "day3.government":
            if debug: print(f"[{time.time()-t0:6.2f}s] run_government 실행")
            return ("government", run_government(
                query,
                pages=int(params.get("pages", 1)),
                items=int(params.get("items", 10)),
                base_year=int(params.get("base_year", 2025)),
            ))
        if tool == "day1.stock":   # ★ 금융 스텝 처리
            if debug: print(f"[{time.time()-t0:6.2f}s] run_stock 실행")
            return ("stock", run_stock(params.get("q") or query))
        return (None, None)

    for s in steps:
        k, v = exec_step(s.get("tool"), s.get("params") or {})
        if k: results[k] = v

    # 최종 포맷
    final_output = decision.get("final_output") or ("government_proposal" if results.get("government") else "research_report")

    if final_output == "government_proposal":
        md = format_government_output(
            query,
            results.get("government") or {"digest_md": "_no government_", "notices": []},
            results.get("rag")
        )
    else:
        structured = compose_report(query, results.get("rag"), results.get("research"), results.get("stock"))
        md = "\n".join([
            f"# Final Report - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"- Query: {query}",
            "",
            structured
        ])

    _save_md(md)
    return md

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-q", "--query", default=os.getenv("D4_QUERY", "최신 클라우드 사업공고를 찾아줘"))
    ap.add_argument("--debug", action="store_true", default=True)
    args = ap.parse_args()
    out = run_router_app(args.query, debug=args.debug)
    print("\n" + "="*60 + "\n")
    print(out[:2000])

if __name__ == "__main__":
    main()
