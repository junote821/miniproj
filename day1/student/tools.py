import os, requests, json, re
from typing import List, Dict, Any
from bs4 import BeautifulSoup

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY", "")
REQUEST_TIMEOUT = int(os.getenv("REQ_TIMEOUT", "15"))
USER_AGENT = os.getenv("USER_AGENT", "Mozilla/5.0 (Day1-Student)")

class WebSearchTool:
    name = "web_search"

    def __init__(self, top_k: int = 5):
        self.top_k = top_k

    def run(self, query: str) -> List[Dict[str, str]]:
        # TODO-6: Tavily API 호출(키 없으면 최소 Mock 1개 반환), {title,url,snippet} 리스트로 정리
        raise NotImplementedError("TODO-6: WebSearchTool.run 구현")

class SummarizeUrlTool:
    name = "summarize_url"

    def __init__(self, summarize_fn, max_chars: int = 4000):
        self.summarize_fn = summarize_fn
        self.max_chars = max_chars

    def _fc_post(self, path: str, payload: dict):
        if not FIRECRAWL_API_KEY:
            return None
        try:
            r = requests.post(
                f"https://api.firecrawl.dev/v1/{path}",
                headers={"Authorization": f"Bearer {FIRECRAWL_API_KEY}",
                         "Content-Type":"application/json"},
                json=payload, timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            return r.json()
        except Exception:
            return None

    def run(self, url: str) -> Dict[str, Any]:
        # TODO-7: Firecrawl /scrape 우선 → 실패 시 requests.get로 HTML→텍스트 추출 → summarize_fn 요약
        # 반환 스키마: {"url": url, "summary": "..."}
        raise NotImplementedError("TODO-7: SummarizeUrlTool.run 구현")
