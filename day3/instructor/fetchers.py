import os, re, time, urllib.parse, requests
from typing import List, Dict, Optional, Set, Tuple
from bs4 import BeautifulSoup

from day3.instructor.parsers import (
    parse_dates, parse_agency, parse_budget, parse_requirements, parse_attachments,
)

REQUEST_TIMEOUT = int(os.getenv("RAG_REQUEST_TIMEOUT", "15"))
USER_AGENT = os.getenv("RAG_USER_AGENT", "Mozilla/5.0 (Day3-NIPA-Instructor)")

NIPA_LIST_URL = os.getenv("NIPA_LIST_URL", "https://www.nipa.kr/home/2-2")
NIPA_MAX_ITEMS = int(os.getenv("NIPA_MAX_ITEMS", "30"))
NIPA_PER_ITEM_BYTES = int(os.getenv("NIPA_PER_ITEM_BYTES", "1200"))

# 부족 시 필터 완화 임계
RELAX_AFTER = int(os.getenv("D3_RELAX_AFTER", "3"))

DETAIL_PAT = re.compile(r"^https?://www\.nipa\.kr/home/2-2/\d+/?$")

WL_DOMAINS = [d.strip().lower() for d in os.getenv(
    "GOV_WEB_WHITELIST",
    "bizinfo.go.kr,nipa.kr,k-startup.go.kr,g2b.go.kr,ntis.go.kr,keiti.re.kr,keit.re.kr"
).split(",") if d.strip()]

TITLE_MUST = ("공고","모집","신청","접수","입찰")
TITLE_BAN = ("주요사업","사업 안내","사업안내","로고","소개","메뉴","요약","뉴스레터")

__all__ = [
    "fetch_nipa_list_by_query",
    "search_web_notices",
    "map_nipa_links_by_keywords",
]

# ------------------------- helpers -------------------------
def _abs_url(base: str, href: str) -> str:
    try:
        return urllib.parse.urljoin(base, href)
    except Exception:
        return href

def _domain(url: str) -> str:
    try:
        return urllib.parse.urlparse(url).netloc.lower()
    except Exception:
        return ""

def _get_html(url: str) -> str:
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    return r.text

def _extract_main_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script","style","noscript","header","footer","nav","aside"]):
        t.decompose()
    selectors = ["div.view-cont","div.board-view","article","div#contents","div#content","section#content","main",".contents"]
    texts=[]
    for sel in selectors:
        node = soup.select_one(sel)
        if node:
            txt = re.sub(r"\s+"," ", node.get_text(" ", strip=True)).strip()
            if txt: texts.append(txt)
    if not texts:
        return re.sub(r"\s+"," ", soup.get_text(" ", strip=True)).strip()
    texts.sort(key=len, reverse=True)
    return texts[0]

def _extract_title(html: str, fallback_url: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for sel in ["div.view-tit h2","h2.tit","div.board-view h2","article h2","h1","h2","title"]:
        node = soup.select_one(sel)
        if node and node.get_text(strip=True):
            return node.get_text(strip=True)
    return fallback_url

def _has_notice_words(text: str) -> bool:
    blob = (text or "").lower()
    return any(k in blob for k in ["공고","모집","신청","접수","입찰"])

def _has_query_words(text: str, query_keywords: List[str]) -> bool:
    blob = (text or "").lower()
    return any(k.lower() in blob for k in (query_keywords or []))

# ------------------------- Progressive filter -------------------------
def _notice_filter_stage(title: str, text: str, attachments: List[Dict],
                         stage: int, query_keywords: List[str]) -> Tuple[bool, str]:
    """stage 1(엄격) → 2(보통) → 3(느슨)"""
    t = (title or "").strip()
    if any(b in t for b in TITLE_BAN):
        return False, "banned_title"

    length = len(text or "")
    has_attach = len(attachments) > 0
    has_title_kw = any(k in t for k in TITLE_MUST)
    has_body_kw = _has_notice_words(text)
    has_query_kw = _has_query_words(text, query_keywords)

    if stage == 1:
        # 제목이 공고형 + (첨부≥1 or 본문≥600자)
        if has_title_kw and (has_attach or length >= 600):
            return True, "stage1_ok"
        return False, "stage1_fail"

    if stage == 2:
        # 제목 비공고라도, 본문에 공고성 키워드 + (첨부≥1 or 본문≥500자)
        if (has_title_kw or has_body_kw) and (has_attach or length >= 500):
            return True, "stage2_ok"
        return False, "stage2_fail"

    # stage == 3
    # 질의 키워드(예: 클라우드) + 본문≥400자
    if (has_title_kw or has_body_kw or has_query_kw) and length >= 400:
        return True, "stage3_ok"
    return False, "stage3_fail"

# ------------------------- NIPA -------------------------
def map_nipa_links_by_keywords(list_url: str, keywords: List[str], max_pages: int) -> List[str]:
    links: Set[str] = set()
    kw_list = [k for k in (keywords or []) if k] or [""]
    for kw in kw_list:
        kw_enc = urllib.parse.quote(kw)
        for page in range(1, max_pages+1):
            url = f"{list_url}?srchKey=title&srchText={kw_enc}&page={page}"
            try:
                html = _get_html(url)
                soup = BeautifulSoup(html, "html.parser")
                kept=0
                for a in soup.find_all("a", href=True):
                    absu = _abs_url(list_url, a["href"])
                    if DETAIL_PAT.match(absu) and absu not in links:
                        links.add(absu); kept += 1
                print(f"[NIPA][map] kw='{kw}' page={page} kept={kept} total={len(links)}")
                time.sleep(0.2)
            except Exception as e:
                print(f"[NIPA][map][ERROR] kw='{kw}' page={page} -> {e}")
    return sorted(links)

def _scrape_detail_nipa(url: str, body_limit: int, stage: int, query_keywords: List[str]) -> Optional[Dict]:
    try:
        html = _get_html(url)
    except Exception as e:
        print(f"[NIPA][detail][ERROR] get_html: {e}")
        return None
    title = _extract_title(html, url)
    text  = _extract_main_text(html)
    attachments = parse_attachments([], base_html=html)

    ok, reason = _notice_filter_stage(title, text, attachments, stage, query_keywords)
    if not ok:
        print(f"[NIPA][filter] stage{stage} drop: {title[:40]}… — {reason}")
        return None

    announce_date, close_date = parse_dates(text)
    snippet = text[:body_limit] if text else title
    content_type = "attachment" if (len(attachments) >= 3 or len(text) < 300) else "text"

    return {
        "title": title, "url": url, "snippet": snippet,
        "date": announce_date or None, "source": "gov-nipa",
        "announce_date": announce_date, "close_date": close_date,
        "agency": parse_agency(text), "budget": parse_budget(text),
        "requirements": parse_requirements(text),
        "attachments": attachments, "content_type": content_type,
        "text_len": len(text), "attach_cnt": len(attachments)
    }

def fetch_nipa_list_by_query(keywords: List[str], list_url: str = NIPA_LIST_URL,
                             max_pages: int = 1, body_limit: int = NIPA_PER_ITEM_BYTES) -> List[Dict]:
    """Progressive: stage1 → stage2 → stage3"""
    detail_urls = map_nipa_links_by_keywords(list_url, keywords, max_pages=max_pages)
    items: List[Dict] = []

    # Stage 1
    for u in detail_urls[:NIPA_MAX_ITEMS]:
        it = _scrape_detail_nipa(u, body_limit, stage=1, query_keywords=keywords)
        if it: items.append(it)
        time.sleep(0.1)
    if len(items) >= RELAX_AFTER:
        return items

    # Stage 2
    for u in detail_urls[:NIPA_MAX_ITEMS]:
        it = _scrape_detail_nipa(u, body_limit, stage=2, query_keywords=keywords)
        if it and (u not in [x["url"] for x in items]): items.append(it)
        if len(items) >= RELAX_AFTER: break
        time.sleep(0.08)
    if len(items) >= RELAX_AFTER:
        return items

    # Stage 3
    for u in detail_urls[:NIPA_MAX_ITEMS]:
        it = _scrape_detail_nipa(u, body_limit, stage=3, query_keywords=keywords)
        if it and (u not in [x["url"] for x in items]): items.append(it)
        time.sleep(0.06)
    return items

# ------------------------- WEB (Day1 검색 활용) -------------------------
def _scrape_detail_web(url: str, body_limit: int, stage: int, query_keywords: List[str]) -> Optional[Dict]:
    try:
        html = _get_html(url)
    except Exception:
        return None
    title = _extract_title(html, url)
    text  = _extract_main_text(html)
    attachments = parse_attachments([], base_html=html)

    ok, reason = _notice_filter_stage(title, text, attachments, stage, query_keywords)
    if not ok:
        return None

    announce_date, close_date = parse_dates(text)
    snippet = text[:body_limit]
    content_type = "attachment" if (len(attachments) >= 3 or len(text) < 300) else "text"
    return {
        "title": title, "url": url, "snippet": snippet,
        "date": announce_date or None, "source": _domain(url) or "web",
        "announce_date": announce_date, "close_date": close_date,
        "agency": parse_agency(text), "budget": parse_budget(text),
        "requirements": parse_requirements(text),
        "attachments": attachments, "content_type": content_type,
        "text_len": len(text), "attach_cnt": len(attachments)
    }

def search_web_notices(query: str, top_n: int = 6, body_limit: int = NIPA_PER_ITEM_BYTES) -> List[Dict]:
    """
    도메인별 쿼리로 확보율 상승:
      - "site:bizinfo.go.kr 공고 {query}"
      - "site:k-startup.go.kr 공고 {query}"
      …
    Progressive filter stage1→2→3 적용.
    """
    try:
        from day1.instructor.tools import WebSearchTool
    except Exception:
        print("[WEB] Day1 WebSearchTool not found")
        return []

    domains = ["bizinfo.go.kr","k-startup.go.kr","nipa.kr","g2b.go.kr","ntis.go.kr","keit.re.kr","keiti.re.kr"]
    queries = [f'site:{d} 공고 {query}' for d in domains]

    search = WebSearchTool(top_k=max(4, top_n // 2))
    cand_urls: List[str] = []
    seen: Set[str] = set()
    for q in queries:
        res = search.run(q) or []
        for r in res:
            url = r.get("url",""); dom = _domain(url)
            if not url or dom not in WL_DOMAINS: continue
            if url in seen: continue
            seen.add(url); cand_urls.append(url)
        time.sleep(0.05)

    items: List[Dict] = []
    # stage 1
    for u in cand_urls:
        it = _scrape_detail_web(u, body_limit, stage=1, query_keywords=[query])
        if it: items.append(it)
        if len(items) >= top_n: break
    if len(items) >= RELAX_AFTER:
        return items[:top_n]

    # stage 2
    for u in cand_urls:
        if any(x["url"] == u for x in items): continue
        it = _scrape_detail_web(u, body_limit, stage=2, query_keywords=[query])
        if it: items.append(it)
        if len(items) >= top_n: break
    if len(items) >= RELAX_AFTER:
        return items[:top_n]

    # stage 3
    for u in cand_urls:
        if any(x["url"] == u for x in items): continue
        it = _scrape_detail_web(u, body_limit, stage=3, query_keywords=[query])
        if it: items.append(it)
        if len(items) >= top_n: break

    return items[:top_n]
