import os, re
from typing import Optional, Tuple, List, Dict
from bs4 import BeautifulSoup
from datetime import datetime, timezone
import zoneinfo

MIN_YEAR = int(os.getenv("NIPA_MIN_YEAR", "2024"))
TZ = zoneinfo.ZoneInfo(os.getenv("TZ", "Asia/Seoul"))

DATE_TOKEN = r"(20\d{2})[.\-/년\s]*(0?[1-9]|1[0-2])[.\-/월\s]*(0?[1-9]|[12]\d|3[01])"
DATE_PAT = re.compile(DATE_TOKEN)
RANGE_PAT = re.compile(DATE_TOKEN + r"\s*[~\-–]\s*" + DATE_TOKEN)

ATTACH_EXT = (".pdf",".hwp",".hwpx",".zip",".xls",".xlsx",".doc",".docx",".ppt",".pptx")

ANN_LABELS = ["공고일","게시일","등록일","공지일"]
CLOSE_LABELS = ["마감","접수마감","제출마감","신청마감","마감일"]
RANGE_LABELS = ["접수기간","신청기간","공고기간","모집기간","기간"]

AGENCY_KEYS = ["주관기관","주최","전담기관","수행기관","기관명","발주처"]
BUDGET_KEYS = ["총사업비","지원규모","예산","지원금액","추정가격"]

def _norm_date(y: str, m: str, d: str) -> str:
    return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"

def _find_dates(text: str) -> List[str]:
    out=[]
    for m in DATE_PAT.finditer(text):
        y, mo, d = m.group(1), m.group(2), m.group(3)
        if int(y) >= MIN_YEAR:
            out.append(_norm_date(y, mo, d))
    return out

def parse_dates(text: str) -> Tuple[Optional[str], Optional[str]]:
    if not text:
        return None, None
    # 1) 기간 표현 우선
    for lab in RANGE_LABELS:
        for m in re.finditer(re.escape(lab), text):
            s, e = max(0, m.start()-180), min(len(text), m.end()+180)
            seg = text[s:e]
            # a ~ b
            for rm in RANGE_PAT.finditer(seg):
                a = _norm_date(rm.group(1),rm.group(2),rm.group(3))
                b = _norm_date(rm.group(4),rm.group(5),rm.group(6))
                return a, b
            # 기간 내에서 날짜 2개 이상
            ds = _find_dates(seg)
            if len(ds)>=2:
                ds.sort()
                return ds[0], ds[-1]
    # 2) 개별 라벨 근처
    def _best_near(labels: List[str]) -> Optional[str]:
        best=None
        for lab in labels:
            for m in re.finditer(re.escape(lab), text):
                s, e = max(0, m.start()-160), min(len(text), m.end()+160)
                seg = text[s:e]
                ds = _find_dates(seg)
                if ds:
                    dmax = max(ds)
                    if (best is None) or (dmax > best): best = dmax
        return best
    announce = _best_near(ANN_LABELS)
    close = _best_near(CLOSE_LABELS)
    return announce, close

def _first_after_label(text: str, keys: List[str], maxlen: int = 80) -> Optional[str]:
    best=None
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
    return _first_after_label(text, AGENCY_KEYS, maxlen=80)

def parse_budget(text: str) -> Optional[str]:
    m = re.search(r"([\d][\d,\.]{0,12})\s*(억원|억|만원|만|원|천만원|백만원)", text)
    if m:
        return f"{m.group(1)}{m.group(2)}"
    return _first_after_label(text, BUDGET_KEYS, maxlen=60)

def parse_requirements(text: str, window: int = 160) -> Optional[str]:
    keys = ["지원대상","신청자격","참여자격","요건","제출서류","평가기준","사업내용","지원내용"]
    hits=[]
    for k in keys:
        for m in re.finditer(re.escape(k), text):
            s, e = max(0, m.start()-window), min(len(text), m.end()+window)
            seg = text[s:e]
            seg = re.sub(r"\s{2,}", " ", seg).strip()
            hits.append(f"{k}: {seg[:300]}")
    if not hits:
        return None
    hits.sort(key=len, reverse=True)
    return hits[0][:400]

def parse_attachments(links: List[Dict], base_html: str = "") -> List[Dict]:
    out=[]
    # HTML에서 첨부 후보
    if base_html:
        soup = BeautifulSoup(base_html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"]; name = a.get_text(strip=True) or ""
            lower = href.lower()
            if lower.endswith(ATTACH_EXT):
                out.append({"name": name or href.split("/")[-1], "url": href})
    # 이미 받은 링크 배열(있다면)
    for it in links or []:
        url = it.get("url") or it.get("href") or ""
        nm = it.get("text") or it.get("title") or ""
        if not url: continue
        low = url.lower()
        if low.endswith(ATTACH_EXT):
            out.append({"name": nm or url.split("/")[-1], "url": url})
    # 중복 제거
    seen=set(); res=[]
    for a in out:
        sig=(a["name"], a["url"])
        if sig in seen: continue
        seen.add(sig); res.append(a)
    return res

# ---- 계산: 마감까지 남은 일수 ----
def compute_days_left(close_date: Optional[str]) -> Optional[int]:
    if not close_date: return None
    try:
        dt = datetime.fromisoformat(close_date).replace(tzinfo=TZ)
        now = datetime.now(TZ)
        return (dt.date() - now.date()).days
    except Exception:
        return None
