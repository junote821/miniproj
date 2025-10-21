import os
from datetime import datetime
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(), override=False)

from day1.student.agents import summarize_text, classify_topic
from day1.student.tools import WebSearchTool, SummarizeUrlTool

def as_markdown(query, label, results, url_summary):
    # TODO-8: 결과를 깔끔한 MD로 렌더(표/리스트 등). 최소한 Query, Domain, Top results, URL Summary 포함
    raise NotImplementedError("TODO-8: as_markdown 구현")

def smoke_run(user_query: str):
    print("=== Day1 Smoke Test (Student) ===")
    label = classify_topic(user_query)
    results = WebSearchTool(top_k=3).run(user_query)
    url_sum = {"url":"", "summary": "(no results)"}
    if results:
        url_sum = SummarizeUrlTool(summarize_text).run(results[0]["url"])
    md = as_markdown(user_query, label, results, url_sum)

    os.makedirs("data/processed", exist_ok=True)
    out_path = "data/processed/day1_snapshot_student.md"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"[Saved] {out_path}")

if __name__ == "__main__":
    q = os.getenv("D1_QUERY","헬스케어 AI 규제 동향 알려줘")
    smoke_run(q)
