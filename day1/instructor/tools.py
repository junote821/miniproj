# day1/instructor/tools.py  (FIXED: no AgentTool base)
import os
import time
import requests
from typing import Any, Dict, List, Callable

REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "12"))

def _retry(fn, tries=2, delay=0.8):
    for i in range(tries):
        try:
            return fn()
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(delay)

class WebSearchTool:
    """
    간단 검색 유틸.
    run(query) -> [{title, url, snippet}]
    """
    def __init__(self, top_k: int = 5):
        self.top_k = top_k
        self.api_key = os.getenv("TAVILY_API_KEY", "")

    def _call_tavily(self, query: str) -> List[Dict[str, str]]:
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
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": (r.get("content", "") or "")[:240],
            }
            for r in results
        ]

    def run(self, query: str) -> List[Dict[str, str]]:
        if not self.api_key:
            return [
                {"title": f"[MOCK] {query} A", "url": "https://example.com/a", "snippet": "샘플 A"},
                {"title": f"[MOCK] {query} B", "url": "https://example.com/b", "snippet": "샘플 B"},
            ]
        try:
            return _retry(lambda: self._call_tavily(query))
        except Exception as e:
            return [{"title": f"[FALLBACK] {query}", "url": "https://example.com", "snippet": f"Error: {e}"}]

class SummarizeUrlTool:
    """
    URL 본문을 가져와 summarize_fn으로 요약.
    run(url) -> {"url": url, "summary": "..."}
    """
    def __init__(self, summarize_fn: Callable[[str], str], max_chars: int = 3000):
        self.summarize_fn = summarize_fn
        self.max_chars = max_chars
        self.fc_key = os.getenv("FIRECRAWL_API_KEY", "")

    def _firecrawl(self, url: str) -> str:
        resp = requests.post(
            "https://api.firecrawl.dev/v1/scrape",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.fc_key}",
            },
            json={"url": url, "formats": ["markdown", "rawText"]},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        return (data.get("markdown") or data.get("rawText") or "")[: self.max_chars]

    def _simple_get(self, url: str) -> str:
        r = requests.get(url, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        return (r.text or "")[: self.max_chars]

    def run(self, url: str) -> Dict[str, Any]:
        text = ""
        if self.fc_key:
            try:
                text = _retry(lambda: self._firecrawl(url))
            except Exception:
                text = ""
        if not text:
            try:
                text = _retry(lambda: self._simple_get(url))
            except Exception as e:
                return {"url": url, "summary": f"[ERROR] failed to fetch: {e}"}
        summary = self.summarize_fn(text)
        return {"url": url, "summary": summary}
