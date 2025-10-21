import os, re
from typing import Optional, Tuple, List, Dict

MIN_YEAR = int(os.getenv("NIPA_MIN_YEAR", "2023"))
NEAR = int(os.getenv("NIPA_NEAR_WINDOW", "120"))

# YYYY-MM-DD / YYYY.MM.DD / YYYY/MM/DD / YYYYMMDD
DATE_TOKEN = r"(20\d{2})[./\- ]?(0[1-9]|1[0-2])[./\- ]?(0[1-9]|[12]\d|3[01])"
DATE_PAT = re.compile(DATE_TOKEN)

ANN_LABELS = ["공고일", "게시일", "등록일", "공지일"]
CLOSE_LABELS = ["마감일", "접수마감", "제출마감", "신청마감"]
RANGE_LABELS = ["접수기간", "신청기간", "공고기간", "모집기간", "기간"]

AGENCY_KEYS = ["주관기관", "주최", "전담기관", "수행기관", "기관명"]
BUDGET_KEYS = ["총사업비", "지원규모", "예산", "지원금액"]
REQ_KEYS = ["핵심", "지원대상", "신청자격", "제출서류", "평가기준", "사업내용", "지원내용", "요건"]

ATTACH_EXT = (".pdf", ".hwp", ".hwpx", ".zip", ".xls", ".xlsx", ".doc", ".docx", ".ppt", ".pptx")

def _norm_date(y: str, m: str, d: str) -> str:
    return f"{y}-{m}-{d}"

def _best_near(text: str, labels: List[str]) -> Optional[str]:
    best = None
    for lab in labels:
        for m in re.finditer(re.escape(lab), text):
            s, e = max(0, m.start()-NEAR), min(len(text), m.end()+NEAR)
            seg = text[s:e]
            for dm in DATE_PAT.finditer(seg):
                y, mo, d = dm.group(1), dm.group(2), dm.group(3)
                if int(y) < MIN_YEAR:
                    continue
                cand = _norm_date(y, mo, d)
                if (best is None) or (cand > best):
                    best = cand
    return best

def parse_dates(text: str) -> Tuple[Optional[str], Optional[str]]:
    if not text:
        return None, None
    # 1) 기간 라벨 근처에서 시작~종료 날짜
    for lab in RANGE_LABELS:
        for m in re.finditer(re.escape(lab), text):
            s, e = max(0, m.start()-NEAR), min(len(text), m.end()+NEAR)
            seg = text[s:e]
            dates = []
            for dm in DATE_PAT.finditer(seg):
                y, mo, d = dm.group(1), dm.group(2), dm.group(3)
                if int(y) < MIN_YEAR:
                    continue
                dates.append(_norm_date(y, mo, d))
            if len(dates) >= 2:
                dates.sort()
                return dates[0], dates[-1]
    # 2) 개별 라벨 근접
    close = _best_near(text, CLOSE_LABELS)
    announce = _best_near(text, ANN_LABELS)
    return announce, close

def _first_after_label(text: str, keys: List[str], maxlen: int = 80) -> Optional[str]:
    best = None
    for k in keys:
        for m in re.finditer(re.escape(k), text):
            s, e = m.end(), min(len(text), m.end()+maxlen)
            seg = text[s:e].strip(" :：-—\n\r\t")
            seg = re.split(r"[。\.\n\r;|]", seg)[0]
            seg = re.sub(r"\s{2,}", " ", seg).strip()
            if seg:
                best = seg if (best is None or len(seg) > len(best)) else best
    return best

def parse_agency(text: str) -> Optional[str]:
    return _first_after_label(text, AGENCY_KEYS, maxlen=60)

def parse_budget(text: str) -> Optional[str]:
    m = re.search(r"([\d][\d,\.]{0,12})\s*(억원|억|만원|만|원)", text)
    if m and int(re.sub(r"[^\d]", "", m.group(1) or "0") or 0) > 0:
        return f"{m.group(1)}{m.group(2)}"
    return _first_after_label(text, BUDGET_KEYS, maxlen=40)

def parse_requirements(text: str, window: int = 160) -> Optional[str]:
    hits = []
    for k in REQ_KEYS:
        for m in re.finditer(re.escape(k), text):
            s, e = max(0, m.start()-window), min(len(text), m.end()+window)
            seg = text[s:e]
            seg = re.sub(r"\s{2,}", " ", seg)
            hits.append(seg.strip())
    if not hits:
        return None
    hits.sort(key=len, reverse=True)
    return hits[0][:400]

def parse_attachments(links: List) -> List[Dict]:
    out: List[Dict] = []
    if not links:
        return out
    for it in links:
        url, name = "", ""
        if isinstance(it, str):
            url = it
        elif isinstance(it, dict):
            url = it.get("url") or it.get("href") or ""
            name = it.get("text") or it.get("title") or ""
        if not url:
            continue
        lower = url.lower()
        if lower.endswith(ATTACH_EXT):
            if not name:
                name = url.split("/")[-1]
            out.append({"name": name, "url": url})
    return out
