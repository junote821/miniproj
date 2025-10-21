import os, requests, re
from typing import List, Dict, Any
from bs4 import BeautifulSoup

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY", "")
REQUEST_TIMEOUT = int(os.getenv("REQ_TIMEOUT","15"))
USER_AGENT = os.getenv("USER_AGENT","Mozilla/5.0 (Day1-Answer)")

class WebSearchTool:
    name="web_search"
    def __init__(self, top_k=5): self.top_k=top_k
    def run(self, query: str) -> List[Dict[str,str]]:
        if not TAVILY_API_KEY:
            return [{"title":"[MOCK] Sample Result","url":"https://example.com",
                     "snippet":"API key missing. This is a mock result."}]
        try:
            r = requests.post("https://api.tavily.com/search",
                json={"api_key": TAVILY_API_KEY, "query": query, "include_answer": False,
                      "max_results": self.top_k},
                timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            data = r.json()
            out=[]
            for it in (data.get("results") or [])[:self.top_k]:
                out.append({"title": it.get("title",""), "url": it.get("url",""),
                            "snippet": it.get("content","")[:300]})
            return out or [{"title":"[EMPTY]","url":"","snippet":"no results"}]
        except Exception as e:
            return [{"title":"[ERROR] Tavily","url":"","snippet":str(e)}]

class SummarizeUrlTool:
    name="summarize_url"
    def __init__(self, summarize_fn, max_chars=4000):
        self.summarize_fn=summarize_fn; self.max_chars=max_chars
    def _fc_post(self, path, payload):
        if not FIRECRAWL_API_KEY: return None
        try:
            r = requests.post(f"https://api.firecrawl.dev/v1/{path}",
                headers={"Authorization": f"Bearer {FIRECRAWL_API_KEY}",
                         "Content-Type":"application/json"},
                json=payload, timeout=REQUEST_TIMEOUT)
            r.raise_for_status(); return r.json()
        except Exception: return None
    def run(self, url: str) -> Dict[str, Any]:
        text=""
        data=self._fc_post("scrape",{
            "url":url,"formats":["markdown","rawText"],"onlyMainContent":True,
            "headers":{"User-Agent":USER_AGENT},"timeout":120000
        })
        if data:
            text = (data.get("rawText") or data.get("markdown") or "")[:self.max_chars]
        if not text:
            try:
                html=requests.get(url, headers={"User-Agent":USER_AGENT}, timeout=REQUEST_TIMEOUT).text
                soup=BeautifulSoup(html,"html.parser")
                for t in soup(["script","style","noscript"]): t.decompose()
                text=re.sub(r"\s+"," ", soup.get_text(" ", strip=True))
                text=text[:self.max_chars]
            except Exception as e:
                return {"url":url, "summary": f"[ERROR] fetch: {e}"}
        return {"url":url, "summary": self.summarize_fn(text)}
