"""
NIPA 목록 페이지에서 상세 공고 링크를 모으고, 상세 페이지에서
타이틀/본문/링크를 가져와 구조화 아이템을 만드는 모듈

이 파일은 '완성본 템플릿'입니다.
핵심 아이디어:
- 목록 수집: Firecrawl map 사용 → 실패시 BeautifulSoup로 폴백
- 상세 수집: Firecrawl scrape 사용 → 실패시 requests.get으로 폴백
- 본문 추출: 메인 컨테이너(div.view-cont 등)에서 가장 긴 텍스트
- 콘텐츠 타입: 텍스트형 vs 첨부형 자동 판별
"""

import os, re, time, urllib.parse, requests
from typing import List, Dict, Optional, Set
from bs4 import BeautifulSoup

from day3.student.parsers import (
    parse_dates, parse_agency, parse_budget, parse_attachments, parse_requirements
)

REQUEST_TIMEOUT = int(os.getenv("RAG_REQUEST_TIMEOUT", "15"))
USER_AGENT = os.getenv("RAG_USER_AGENT", "Mozilla/5.0 (Day3-Student)")
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY", "")

NIPA_LIST_URL = os.getenv("NIPA_LIST_URL", "https://www.nipa.kr/home/2-2")
NIPA_MAX_PAGES = int(os.getenv("NIPA_MAX_PAGES", "1"))
NIPA_PER_ITEM_BYTES = int(os.getenv("NIPA_PER_ITEM_BYTES", "900"))
NIPA_MAX_ITEMS = int(os.getenv("NIPA_MAX_ITEMS", "10"))

DETAIL_PAT = re.compile(r"^https?://www\.nipa\.kr/home/2-2/\d+/?$")


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
    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    return re.sub(r"\s+", " ", soup.get_text(" ", strip=True)).strip()


def _fc_post(path: str, payload: dict) -> Optional[dict]:
    if not FIRECRAWL_API_KEY:
        return None
    try:
        r = requests.post(
            f"https://api.firecrawl.dev/v1/{path}",
            headers={
                "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def map_nipa_links(list_url: str, max_pages: int) -> List[str]:
    """목록 페이지에서 상세 공고 URL만 수집."""
    links: Set[str] = set()
    for page in range(1, max_pages + 1):
        url = list_url if page == 1 else f"{list_url}?page={page}"
        data = _fc_post("map", {"url": url, "timeout": 120000})
        if data and isinstance(data, dict) and "links" in data:
            candidates = data.get("links") or []
        else:
            try:
                html = _get_html(url)
                soup = BeautifulSoup(html, "html.parser")
                candidates = [
                    _abs_url(list_url, a.get("href") or "")
                    for a in soup.find_all("a")
                    if a.get("href")
                ]
            except Exception:
                candidates = []
        kept = 0
        for u in candidates:
            if isinstance(u, str) and DETAIL_PAT.match(u.strip()):
                links.add(u.strip())
                kept += 1
        print(f"[map] page={page} kept={kept} total={len(links)}")
        time.sleep(0.1)
    return sorted(links)


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


MAIN_SELECTORS = [
    "div.view-cont", "div.board-view", "article", "div#contents", "div#content", "section#content", "main",
]


def _extract_main_text(html: str) -> str:
    """메뉴/푸터 제거 후 메인 컨테이너 후보에서 가장 긴 텍스트를 선택."""
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript", "header", "footer", "nav", "aside"]):
        t.decompose()
    texts = []
    for sel in MAIN_SELECTORS:
        node = soup.select_one(sel)
        if node:
            txt = re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()
            if txt:
                texts.append(txt)
    if not texts:
        return re.sub(r"\s+", " ", soup.get_text(" ", strip=True)).strip()
    texts.sort(key=len, reverse=True)
    return texts[0]


def scrape_detail(url: str, body_limit: int = 900) -> Dict:
    """상세 페이지에서 아이템 1개 수집 + 구조화."""
    data = _fc_post(
        "scrape",
        {
            "url": url,
            "formats": ["markdown", "links", "html"],
            "onlyMainContent": True,
            "headers": {"User-Agent": USER_AGENT},
            "timeout": 120000,
        },
    )
    title, markdown, links, html = "", "", [], ""
    if data:
        title = (data.get("metadata", {}) or {}).get("title") or ""
        markdown = data.get("markdown") or ""
        links = data.get("links") or []
        html = data.get("html") or ""

    if not html:
        try:
            html = _get_html(url)
        except Exception:
            html = ""

    if html:
        ttl = _extract_title_from_html(html)
        if ttl:
            title = ttl
        main_text = _extract_main_text(html)
        if not markdown or (len(main_text) > len(markdown) * 0.7):
            markdown = main_text

    snippet = (markdown[:body_limit] if markdown else (title or url))

    # 구조 필드
    announce_date, close_date = parse_dates(markdown)
    agency = parse_agency(markdown)
    budget = parse_budget(markdown)
    requirements = parse_requirements(markdown)
    attachments = parse_attachments(links)

    # 텍스트형 vs 첨부형 판별
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


def fetch_nipa_list(
    list_url: str = NIPA_LIST_URL, max_pages: int = NIPA_MAX_PAGES, body_limit: int = NIPA_PER_ITEM_BYTES
) -> List[Dict]:
    detail_urls = map_nipa_links(list_url, max_pages=max_pages)
    items: List[Dict] = []
    for idx, u in enumerate(detail_urls[: NIPA_MAX_ITEMS], 1):
        print(f"[detail] {idx}/{min(len(detail_urls), NIPA_MAX_ITEMS)} → {u}")
        try:
            items.append(scrape_detail(u, body_limit=body_limit))
        except Exception as e:
            items.append(
                {
                    "title": "[ERROR] 상세 파싱 실패",
                    "url": u,
                    "snippet": str(e),
                    "date": None,
                    "source": "gov-nipa",
                }
            )
        time.sleep(0.1)
    if len(detail_urls) > NIPA_MAX_ITEMS:
        print(f"[NIPA] Skipped {len(detail_urls) - NIPA_MAX_ITEMS} items (limited by NIPA_MAX_ITEMS).")
    return items
