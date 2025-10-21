import os, re, time, urllib.parse, requests
from typing import List, Dict, Optional, Set
from bs4 import BeautifulSoup

from day3.instructor.parsers import (
    parse_dates, parse_agency, parse_budget, parse_attachments, parse_requirements
)

REQUEST_TIMEOUT = int(os.getenv("RAG_REQUEST_TIMEOUT", "15"))
USER_AGENT = os.getenv("RAG_USER_AGENT", "Mozilla/5.0 (Day3-NIPA-Instructor)")
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY", "")

# 기본 목록 URL (검색 파라미터 적용 가능)
NIPA_LIST_URL = os.getenv("NIPA_LIST_URL", "https://www.nipa.kr/home/2-2")
NIPA_MAX_PAGES = int(os.getenv("NIPA_MAX_PAGES", "3"))
NIPA_PER_ITEM_BYTES = int(os.getenv("NIPA_PER_ITEM_BYTES", "900"))
NIPA_MAX_ITEMS = int(os.getenv("NIPA_MAX_ITEMS", "20"))

# 상세 URL 패턴
DETAIL_PAT = re.compile(r"^https?://www\.nipa\.kr/home/2-2/\d+/?$")

# --- 공통 유틸 ---
def _abs_url(base: str, href: str) -> str:
    try:
        return urllib.parse.urljoin(base, href)
    except Exception:
        return href

def _get_html(url: str) -> str:
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    return r.text

def _textify(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script","style","noscript","header","footer","nav","aside"]):
        t.decompose()
    return re.sub(r"\s+"," ", soup.get_text(" ", strip=True)).strip()

def _fc_post(path: str, payload: dict) -> Optional[dict]:
    if not FIRECRAWL_API_KEY:
        return None
    try:
        r = requests.post(
            f"https://api.firecrawl.dev/v1/{path}",
            headers={"Authorization": f"Bearer {FIRECRAWL_API_KEY}", "Content-Type":"application/json"},
            json=payload, timeout=REQUEST_TIMEOUT
        )
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

# --- 목록 수집(질의 키워드 기반) ---
def map_nipa_links_by_keywords(list_url: str, keywords: List[str], max_pages: int) -> List[str]:
    """
    질의 키워드를 NIPA 목록 페이지의 '키워드검색' 파라미터(srchText)로 주입하여
    실제 공고 목록 영역에서 상세 링크(/home/2-2/{id})만 수집한다.
    """
    links: Set[str] = set()
    kw_list = [k for k in (keywords or []) if k]
    if not kw_list:
        kw_list = [""]  # 키워드가 없으면 전체(빈 검색)

    for kw in kw_list:
        kw_enc = urllib.parse.quote(kw)
        for page in range(1, max_pages+1):
            # 페이지네이션이 서버쪽에 어떤 파라미터를 쓰는지는 페이지 구조에 따라 다름.
            # 기본은 srchText만으로도 최신순 일부가 노출되므로 page=는 우선 생략(필요시 추가).
            url = f"{list_url}?srchKey=title&srchText={kw_enc}"
            try:
                html = _get_html(url)
                soup = BeautifulSoup(html, "html.parser")
                # 목록 테이블/리스트 영역에서 상세 링크 추출
                cand_urls: List[str] = []
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    absu = _abs_url(list_url, href)
                    if DETAIL_PAT.match(absu):
                        cand_urls.append(absu)
                kept = 0
                for u in cand_urls:
                    if u not in links:
                        links.add(u); kept += 1
                print(f"[NIPA][map-kw] kw='{kw}' page={page} kept={kept} total_links={len(links)}")
                time.sleep(0.2)
            except Exception as e:
                print(f"[NIPA][map-kw][ERROR] kw='{kw}' page={page} -> {e}")
                continue

    # 키워드로도 충분히 못 모았다면(방화벽/봇차단 등) Firecrawl map로 보완
    if not links:
        print("[NIPA][map-kw] fallback to Firecrawl map (no links via HTML)")
        for page in range(1, max_pages+1):
            url = list_url if page == 1 else f"{list_url}?page={page}"
            data = _fc_post("map", {"url": url, "timeout": 120000})
            candidates = (data or {}).get("links") or []
            kept = 0
            for u in candidates:
                if isinstance(u, str) and DETAIL_PAT.match(u.strip()):
                    links.add(u.strip()); kept += 1
            print(f"[NIPA][map-fc] page={page} kept={kept} total_links={len(links)}")
            time.sleep(0.2)

    return sorted(links)

# --- 본문/타이틀 추출 ---
def _extract_title_from_html(html: str) -> Optional[str]:
    soup = BeautifulSoup(html, "html.parser")
    for sel in ["div.view-tit h2", "h2.tit", "div.board-view h2", "article h2", "h1", "h2"]:
        node = soup.select_one(sel)
        if node and node.get_text(strip=True):
            return node.get_text(strip=True)
    og = soup.find("meta", attrs={"property": "og:title"})
    if og and og.get("content"):
        return og.get("content").strip()
    if soup.title and soup.title.get_text(strip=True):
        return soup.title.get_text(strip=True)
    return None

def _extract_main_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script","style","noscript","header","footer","nav","aside"]):
        t.decompose()
    selectors = ["div.view-cont","div.board-view","article","div#contents","div#content","section#content","main"]
    texts = []
    for sel in selectors:
        node = soup.select_one(sel)
        if node:
            txt = re.sub(r"\s+"," ", node.get_text(" ", strip=True)).strip()
            if txt:
                texts.append(txt)
    if not texts:
        return re.sub(r"\s+"," ", soup.get_text(" ", strip=True)).strip()
    texts.sort(key=len, reverse=True)
    return texts[0]

# --- 상세 스크레이핑 ---
def scrape_detail(url: str, body_limit: int = 900) -> Dict:
    """
    Returns item dict:
      {title,url,snippet,date,source,links,
       announce_date,close_date,agency,budget,requirements,attachments,
       content_type,text_len,attach_cnt}
    """
    # 1) Firecrawl scrape 시도 (markdown/links/html)
    data = _fc_post("scrape", {
        "url": url,
        "formats": ["markdown","links","html"],
        "onlyMainContent": True,
        "headers": {"User-Agent": USER_AGENT},
        "timeout": 120000
    })
    title, markdown, links, html = "", "", [], ""
    if data:
        title = (data.get("metadata",{}) or {}).get("title") or ""
        markdown = data.get("markdown") or ""
        links = data.get("links") or []
        html = data.get("html") or ""

    # 2) 폴백: requests + BS4
    if not html:
        try:
            html = _get_html(url)
        except Exception:
            html = ""

    # 3) 타이틀/본문 보정
    if html:
        ttl = _extract_title_from_html(html)
        if ttl: title = ttl
        main_text = _extract_main_text(html)
        if not markdown or (len(main_text) > len(markdown) * 0.7):
            markdown = main_text

    snippet = (markdown[:body_limit] if markdown else (title or url))

    # 4) 구조 필드 추출
    announce_date, close_date = parse_dates(markdown)
    agency = parse_agency(markdown)
    budget = parse_budget(markdown)
    requirements = parse_requirements(markdown)
    attachments = parse_attachments(links)

    # 5) 콘텐츠 타입 판별
    text_len = len(markdown or "")
    attach_cnt = len(attachments)
    content_type = "attachment" if (attach_cnt >= 3 or text_len < 300) else "text"

    return {
        "title": title or url,
        "url": url,
        "snippet": snippet,
        "date": announce_date or None,
        "source": "gov-nipa",
        "links": links,
        "announce_date": announce_date,
        "close_date": close_date,
        "agency": agency,
        "budget": budget,
        "requirements": requirements,
        "attachments": attachments,
        "content_type": content_type,
        "text_len": text_len,
        "attach_cnt": attach_cnt,
    }

# --- 메인 수집 함수 ---
def fetch_nipa_list_by_query(keywords: List[str],
                             list_url: str = NIPA_LIST_URL,
                             max_pages: int = NIPA_MAX_PAGES,
                             body_limit: int = NIPA_PER_ITEM_BYTES) -> List[Dict]:
    detail_urls = map_nipa_links_by_keywords(list_url, keywords, max_pages=max_pages)
    items: List[Dict] = []
    for idx, u in enumerate(detail_urls[:NIPA_MAX_ITEMS], 1):
        try:
            print(f"[NIPA][detail] {idx}/{min(len(detail_urls), NIPA_MAX_ITEMS)} → {u}")
            items.append(scrape_detail(u, body_limit=body_limit))
            time.sleep(0.2)
        except Exception as e:
            items.append({"title":"[GOV ERROR] 상세 파싱 실패","url":u,"snippet":str(e),
                          "date":None,"source":"gov-nipa"})
    if len(detail_urls) > NIPA_MAX_ITEMS:
        print(f"[NIPA] Skipped {len(detail_urls) - NIPA_MAX_ITEMS} items (limited by NIPA_MAX_ITEMS).")
    return items
