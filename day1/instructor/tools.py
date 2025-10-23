import os
import re
import time
import requests
from typing import Any, Dict, List, Callable, Optional

REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "12"))

def _retry(fn, tries=2, delay=0.8):
    for i in range(tries):
        try:
            return fn()
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(delay)

# --- 간단한 노이즈 제거 (요약 전에 1차 정리) ---
_NOISE_BLOCK = re.compile(
    r"(개인정보 처리방침|개인정보처리방침|이용약관|사이트맵|고객센터|관련사이트|상단으로|"
    r"바로가기|주요사업|윤리경영|ESG|인권경영|공시|스크립트가 비활성화|자바스크립트|"
    r"메뉴|푸터|네비게이션|로그인|회원가입)", re.I
)

def _clean_web_text(t: str, max_chars: int) -> str:
    if not t:
        return ""
    # 너무 긴 문서면 먼저 자르고
    t = t[: max_chars * 2]
    # 코드/스크립트 흔적 간단 제거
    t = re.sub(r"<script[\s\S]*?</script>", " ", t, flags=re.I)
    t = re.sub(r"<style[\s\S]*?</style>", " ", t, flags=re.I)
    # 노이즈 키워드 이후는 과감히 컷 (대부분 푸터/전사 메뉴)
    m = _NOISE_BLOCK.search(t)
    if m:
        t = t[: m.start()]
    # 공백 정리
    t = re.sub(r"\s+", " ", t)
    return t.strip()[: max_chars]

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
            # 오프라인/테스트 모드
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
        text = (data.get("markdown") or data.get("rawText") or "")
        return _clean_web_text(text, self.max_chars)

    def _simple_get(self, url: str) -> str:
        r = requests.get(url, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        return _clean_web_text(r.text or "", self.max_chars)

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


# ----------------- yfinance StockPriceTool -----------------
try:
    import yfinance as yf
except Exception:
    yf = None

_KR_TICKER_HINTS = {
    "삼성전자": "005930.KS",
    "삼성전자우": "005935.KS",
}

def _guess_ticker(query: str) -> Optional[str]:
    q = (query or "").lower()
    # 숫자 티커
    m = re.findall(r"\b(005930|005935)\b", q)
    if m:
        return (m[0] + ".KS")
    # 한글 이름 힌트
    for k,v in _KR_TICKER_HINTS.items():
        if k in query:
            return v
    # 영문명 힌트
    if "samsung electronics" in q:
        return "005930.KS"
    return None

class StockPriceTool:
    """
    yfinance 기반 단순 스냅샷
    out:
      {"symbol","name","price","change","change_pct","currency","market_time","open","high","low","prev_close","volume","market_cap"}
    """
    def run(self, query_or_symbol: str) -> Dict[str, Any]:
        if yf is None:
            return {"error":"yfinance_not_installed"}
        sym = query_or_symbol
        if not re.search(r"[A-Za-z]{1,5}\.[A-Z]{2}|^\d{5}\.KS$", sym):
            hint = _guess_ticker(query_or_symbol)
            if hint: sym = hint
        try:
            t = yf.Ticker(sym)
            info = t.fast_info  # 빠르고 안전
            price = float(info.get("last_price") or 0.0)
            prev = float(info.get("previous_close") or 0.0)
            ch = price - prev if prev else 0.0
            ch_pct = (ch / prev * 100.0) if prev else 0.0
            out = {
                "symbol": sym,
                "name": "Samsung Electronics" if sym.startswith("00593") else sym,
                "price": price,
                "change": ch,
                "change_pct": ch_pct,
                "currency": info.get("currency") or "KRW",
                "market_time": int(info.get("last_price_time") or 0),
                "open": float(info.get("open") or 0.0),
                "high": float(info.get("day_high") or 0.0),
                "low": float(info.get("day_low") or 0.0),
                "prev_close": prev,
                "volume": int(info.get("last_volume") or 0),
                "market_cap": float(info.get("market_cap") or 0.0),
                "provider": "yfinance",
            }
            return out
        except Exception as e:
            return {"symbol": sym, "error": f"{e}"}
