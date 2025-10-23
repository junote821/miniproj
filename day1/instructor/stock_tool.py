import re
from typing import Dict, Any
import yfinance as yf

_KR_TICKER_MAP = {
    "삼성전자": "005930.KS",
    "카카오": "035720.KS",
    "네이버": "035420.KS",
    "현대차": "005380.KS",
    "LG에너지솔루션": "373220.KS",
}

_CODE_PAT = re.compile(r"\b(005930|035720|035420|005380|373220)\b")

def _guess_ticker(q: str) -> str | None:
    q = (q or "").strip()
    # 코드 직접 입력
    m = _CODE_PAT.search(q)
    if m:
        code = m.group(1)
        return f"{code}.KS"
    # 한글명 매핑
    for name, sym in _KR_TICKER_MAP.items():
        if name in q:
            return sym
    # 영문 직접 심볼 입력
    if re.search(r"[A-Za-z]{1,5}\.?[A-Za-z]*", q):
        return q.strip()
    return None

class StockPriceTool:
    """yfinance 기반 간단 스냅샷 도구"""
    def run(self, query_or_symbol: str) -> Dict[str, Any]:
        symbol = _guess_ticker(query_or_symbol) or query_or_symbol
        try:
            t = yf.Ticker(symbol)
            info = t.info or {}
            hist = t.history(period="5d", interval="1d")
            price = (
                info.get("regularMarketPrice")
                or info.get("currentPrice")
                or (hist["Close"].iloc[-1] if hasattr(hist, "__getitem__") and not hist.empty else None)
            )
            if price is None or float(price) == 0.0:
                return {"error": "가격 데이터 없음(시장 휴장/네트워크/심볼 불일치 가능)", "symbol": symbol}

            prev = (
                info.get("regularMarketPreviousClose")
                or (hist["Close"].iloc[-2] if hasattr(hist, "__getitem__") and len(hist) > 1 else None)
            )
            change = (price - prev) if (isinstance(price, (int,float)) and isinstance(prev,(int,float))) else 0.0
            change_pct = (change/prev*100.0) if prev and prev != 0 else 0.0

            return {
                "symbol": symbol,
                "currency": info.get("currency") or "KRW",
                "price": float(price),
                "open": float(info.get("open") or (hist["Open"].iloc[-1] if not hist.empty else 0.0)),
                "high": float(info.get("dayHigh") or (hist["High"].iloc[-1] if not hist.empty else 0.0)),
                "low":  float(info.get("dayLow")  or (hist["Low"].iloc[-1]  if not hist.empty else 0.0)),
                "volume": int(info.get("volume") or 0),
                "market_cap": float(info.get("marketCap") or 0.0),
                "change": float(change),
                "change_pct": float(change_pct),
            }
        except Exception as e:
            return {"error": f"yfinance error: {e}", "symbol": symbol}
