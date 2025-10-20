# Day1 템플릿
# 역할:
#  - WebSearchTool v1: Tavily 간단 검색 → 상위 n개 결과(제목/URL/요약)
#  - SummarizeUrlTool: URL 본문을 가져와 요약 (Firecrawl 권장, 실패 시 아주 간단 폴백)
#
# 구현 포인트:
#  - .env 에서 키를 읽고, 키가 없으면 "학습용 목업"을 반환
#  - 실제 운영 시에는 예외처리/재시도/타임아웃을 더 견고히!

import os
import json
import time
import requests
from typing import Any, Dict, List, Optional

REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "12"))

# ----- WebSearchTool (Tavily) -----
class WebSearchTool:
    name = "web_search"
    description = "Search the web for recent information. Returns a list of {title, url, snippet}."

    def __init__(self, top_k: int = 5):
        super().__init__()
        self.top_k = top_k
        self.api_key = os.getenv("TAVILY_API_KEY", "")

    def run(self, query: str) -> List[Dict[str, str]]:
        if not self.api_key:
            # 목업(키 없을 때) -> 구현 때는 실제 키 설정
            return [
                {"title": f"[MOCK] {query} 1", "url": "https://example.com/1", "snippet": "샘플 스니펫 1"},
                {"title": f"[MOCK] {query} 2", "url": "https://example.com/2", "snippet": "샘플 스니펫 2"},
            ]

        try:
            resp = requests.post(
                "https://api.tavily.com/search",
                headers={"Content-Type": "application/json"},
                json={
                    "api_key": self.api_key,
                    "query": query,
                    "max_results": self.top_k,
                    "include_answer": False,
                },
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])[: self.top_k]
            out = []
            for r in results:
                out.append(
                    {
                        "title": r.get("title", ""),
                        "url": r.get("url", ""),
                        "snippet": r.get("content", "")[:240],
                    }
                )
            return out
        except Exception as e:
            # 간단 폴백
            return [
                {"title": f"[FALLBACK] {query}", "url": "https://example.com", "snippet": f"Error: {e}"}
            ]

# ----- SummarizeUrlTool (Firecrawl) -----
class SummarizeUrlTool:
    name = "summarize_url"
    description = "Fetch a URL and return a short summary. Prefers Firecrawl; falls back to basic extraction."

    def __init__(self, summarize_fn, max_chars: int = 2000):
        """
        summarize_fn: (str) -> str  # SummarizerAgent의 summarize_text 함수 주입
        """
        super().__init__()
        self.summarize_fn = summarize_fn
        self.max_chars = max_chars
        self.fc_key = os.getenv("FIRECRAWL_API_KEY", "")

    def run(self, url: str) -> Dict[str, Any]:
        text = None
        # 1) Firecrawl 우선
        if self.fc_key:
            try:
                resp = requests.post(
                    "https://api.firecrawl.dev/v1/scrape",
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.fc_key}",
                    },
                    json={"url": url, "formats": ["markdown", "html", "rawText"]},
                    timeout=REQUEST_TIMEOUT,
                )
                resp.raise_for_status()
                data = resp.json()
                text = (
                    data.get("markdown")
                    or data.get("rawText")
                    or data.get("html")
                    or ""
                )
            except Exception:
                text = None

        # 2) 폴백: 간단 GET (동적 사이트는 실패할 수 있음)
        if not text:
            try:
                r = requests.get(url, timeout=REQUEST_TIMEOUT)
                r.raise_for_status()
                # 아주 단순: HTML에서 텍스트만 대충 슬라이스
                text = r.text
            except Exception as e:
                return {"url": url, "summary": f"[FALLBACK ERROR] {e}"}

        text = text[: self.max_chars]
        summary = self.summarize_fn(text)
        return {"url": url, "summary": summary}
