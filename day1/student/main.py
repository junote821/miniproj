# Day1 템플릿
# - Agent(요약/분류) + Tool(웹검색/URL요약) 조합 스모크 테스트
# - event.content.parts 구조를 가볍게 확인

import os
from day1.student.agents import summarize_text, classify_topic
from day1.student.tools import WebSearchTool, SummarizeUrlTool

def smoke_run(user_query: str):
    print("=== Day1 Smoke Test ===")
    print("User Query:", user_query)

    label = classify_topic(user_query)
    print("Domain Label:", label)

    search = WebSearchTool(top_k=3)
    results = search.run(user_query)
    print("\n[Web Search Top-3]")
    for i, r in enumerate(results, 1):
        print(f"{i}. {r['title']} -> {r['url']}")

    if results:
        url = results[0]["url"]
        sum_tool = SummarizeUrlTool(summarize_text)
        s = sum_tool.run(url)
        print("\n[URL Summary]")
        print("URL:", s["url"])
        print("Summary:", s["summary"])

if __name__ == "__main__":
    q = "헬스케어 AI 규제 동향 알려줘"
    smoke_run(q)
