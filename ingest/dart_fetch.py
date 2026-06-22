"""DART 수집: 기업명 → corp_code/ticker/market, 최신 사업보고서 평문, 과거 공시 일자.

API 키(OpenDartReader)가 없거나 네트워크가 불가하면 내장 샘플로 graceful fallback 하여
MVP 시연이 항상 가능하도록 한다.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, asdict
from datetime import date, timedelta
from typing import List, Optional

from utils import ensure_root_on_path, normalize_text, ttl_cache

ensure_root_on_path()
import config  # noqa: E402


# ---------------------------------------------------------------------------
# 내장 샘플 (오프라인/무키 시연용)
# ---------------------------------------------------------------------------
SAMPLE_CORP = {
    "삼성전자": {"ticker": "005930", "corp_code": "00126380", "market": "KOSPI"},
    "SK하이닉스": {"ticker": "000660", "corp_code": "00164779", "market": "KOSPI"},
    "NAVER": {"ticker": "035420", "corp_code": "00266961", "market": "KOSPI"},
    "카카오": {"ticker": "035720", "corp_code": "00258801", "market": "KOSPI"},
}

_SAMPLE_REPORT_TEXT = {
    "005930": (
        "삼성전자 사업보고서(요약 샘플). 당사는 반도체(DS), 디바이스경험(DX), SDC, Harman "
        "부문으로 구성된다. 매출액은 전년 대비 증가하였으며 반도체 부문은 메모리 업황 회복과 "
        "HBM(고대역폭메모리) 등 고부가 제품 수요 확대로 영업이익이 개선되었다. DX 부문은 "
        "스마트폰과 가전의 프리미엄 전략을 지속하고 있다. 당사는 주주환원 정책의 일환으로 "
        "분기 배당을 실시하며 자기주식 취득 및 소각을 검토한다. 주요 리스크로는 메모리 가격 "
        "변동성, 환율, 글로벌 수요 둔화, 미·중 통상 규제, 첨단공정 투자 부담이 있다. 현금흐름은 "
        "영업활동에서 견조하게 창출되고 있으며 연구개발 투자를 지속 확대한다. HBM 생산능력 "
        "확대와 파운드리 선단공정 수율 개선이 향후 실적의 핵심 변수다."
    ),
    "000660": (
        "SK하이닉스 사업보고서(요약 샘플). 당사는 D램과 낸드플래시 메모리를 생산한다. "
        "AI 서버 수요 확대로 HBM 매출이 빠르게 증가하며 수익성이 크게 개선되었다. 주요 리스크는 "
        "메모리 사이클 변동성, 대규모 설비투자(CAPEX) 부담, 환율 및 지정학 리스크다. 배당 정책과 "
        "재무구조 개선을 추진하고 있다."
    ),
}

# 최근 공시 목록 샘플(오프라인/무키 시연용) — DART 키가 있으면 실제 목록으로 대체됨
_SAMPLE_DISCLOSURES = {
    "005930": [
        {"title": "분기보고서 (2026.03)", "date": "2026-05-15"},
        {"title": "현금ㆍ현물배당 결정", "date": "2026-04-30"},
        {"title": "매출액또는손익구조30%(대규모법인은15%)이상변동", "date": "2026-04-30"},
        {"title": "주식소각 결정", "date": "2026-04-09"},
        {"title": "사업보고서 (2025.12)", "date": "2026-03-11"},
    ],
}


@dataclass
class CorpInfo:
    company: str
    ticker: str
    corp_code: str
    market: str


# ---------------------------------------------------------------------------
# OpenDartReader 인스턴스 (지연 생성)
# ---------------------------------------------------------------------------
def _get_dart():
    if not config.DART_API_KEY:
        return None
    # 패키지 버전에 따라 import 경로가 다르다:
    #  - 0.3.x: `from opendartreader import OpenDartReader`
    #  - 0.2.x: `import OpenDartReader` (top-level가 클래스/모듈)
    OpenDartReader = None
    try:
        from opendartreader import OpenDartReader  # noqa: N813 (0.3.x)
    except Exception:
        try:
            import OpenDartReader as _od  # 0.2.x

            OpenDartReader = getattr(_od, "OpenDartReader", _od)
        except Exception:
            return None
    try:
        return OpenDartReader(config.DART_API_KEY)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# corp_master 캐시
# ---------------------------------------------------------------------------
def _read_master() -> dict:
    out = {}
    if config.CORP_MASTER_CSV.exists():
        with open(config.CORP_MASTER_CSV, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                out[row["company"]] = row
    return out


def _write_master(rows: dict) -> None:
    config.CORP_MASTER_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(config.CORP_MASTER_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["company", "ticker", "corp_code", "market"])
        w.writeheader()
        for r in rows.values():
            w.writerow({k: r[k] for k in w.fieldnames})


def resolve_corp(company: str) -> Optional[CorpInfo]:
    """기업명 → CorpInfo. 캐시 → 샘플 → DART 순으로 조회하고 캐시에 저장."""
    company = company.strip()
    master = _read_master()
    if company in master:
        m = master[company]
        return CorpInfo(company, m["ticker"], m["corp_code"], m["market"])

    info: Optional[CorpInfo] = None
    if company in SAMPLE_CORP:
        s = SAMPLE_CORP[company]
        info = CorpInfo(company, s["ticker"], s["corp_code"], s["market"])
    else:
        dart = _get_dart()
        if dart is not None:
            try:
                corp_code = dart.find_corp_code(company)
                if corp_code:
                    # ticker/market은 corp_code 기준 기업개황에서 추출
                    ticker, market = "", "KOSPI"
                    try:
                        c = dart.company(str(corp_code))
                        ticker = (c.get("stock_code") or "").strip()
                        # corp_cls: Y=KOSPI(유가), K=KOSDAQ(코스닥), N=KONEX, E=기타
                        cls = (c.get("corp_cls") or "Y").strip().upper()
                        market = {"Y": "KOSPI", "K": "KOSDAQ"}.get(cls, "KOSPI")
                    except Exception:
                        pass
                    # 상장 종목코드가 없으면(비상장 등) 분석 대상에서 제외
                    if ticker:
                        info = CorpInfo(company, ticker, str(corp_code), market)
            except Exception:
                info = None

    if info is not None:
        master[company] = asdict(info)
        _write_master(master)
    return info


def fetch_latest_report(company: str) -> Optional[dict]:
    """최신 정기보고서(사업/반기/분기) 평문 텍스트와 rcept_no를 반환."""
    info = resolve_corp(company)
    if info is None:
        return None

    dart = _get_dart()
    if dart is not None:
        try:
            start = f"{date.today().year - 2}-01-01"
            # 이름이 아닌 corp_code로 조회(이름 매칭이 일부 기업에서 실패함)
            lst = dart.list(info.corp_code, start=start, kind="A")
            if lst is not None and len(lst) > 0:
                rcept_no = str(lst.iloc[0]["rcept_no"])
                raw = dart.document_all(rcept_no)
                # document_all은 버전에 따라 str 또는 XML 문자열 list를 반환한다.
                if isinstance(raw, (list, tuple)):
                    raw = "\n".join(str(x) for x in raw)
                text = normalize_text(raw if isinstance(raw, str) else str(raw))
                if text:
                    out_path = config.RAW_REPORTS_DIR / f"{info.ticker}_{rcept_no}.txt"
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    out_path.write_text(text, encoding="utf-8")
                    return {"ticker": info.ticker, "rcept_no": rcept_no, "text": text}
        except Exception:
            pass

    # fallback: 내장 샘플
    text = _SAMPLE_REPORT_TEXT.get(info.ticker)
    if text:
        rcept_no = f"SAMPLE_{info.ticker}"
        out_path = config.RAW_REPORTS_DIR / f"{info.ticker}_{rcept_no}.txt"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
        return {"ticker": info.ticker, "rcept_no": rcept_no, "text": text}
    return None


@ttl_cache(seconds=1800)  # 30분: 공시 일자는 자주 바뀌지 않음
def fetch_event_dates(company: str, kind: str = "A", n: int = None) -> List[str]:
    """과거 동일 유형 공시(정기보고서 등)의 접수일 목록(YYYY-MM-DD). 주가 반응 이벤트로 사용."""
    n = n or config.PRICE_MAX_EVENTS
    info = resolve_corp(company)
    if info is None:
        return []

    dart = _get_dart()
    if dart is not None:
        try:
            start = f"{date.today().year - 5}-01-01"
            lst = dart.list(info.corp_code, start=start, kind=kind)
            if lst is not None and len(lst) > 0:
                dates = []
                for raw in lst["rcept_dt"].astype(str).tolist()[:n]:
                    raw = raw.strip()
                    if len(raw) == 8:  # YYYYMMDD
                        dates.append(f"{raw[:4]}-{raw[4:6]}-{raw[6:]}")
                    else:
                        dates.append(raw)
                if dates:
                    return dates
        except Exception:
            pass

    # fallback: 분기 간격의 합성 이벤트 일자(시연용)
    today = date.today()
    return [
        (today - timedelta(days=90 * (i + 1))).isoformat() for i in range(min(n, 12))
    ]


@ttl_cache(seconds=1800)  # 30분 캐시: 화면 표시용 최근 공시 목록
def fetch_recent_disclosures(company: str, n: int = 10) -> List[dict]:
    """최근 공시 목록(전 유형) → [{title, date, rcept_no, url}]. UI 링크용."""
    info = resolve_corp(company)
    if info is None:
        return []

    dart = _get_dart()
    if dart is not None:
        try:
            start = f"{date.today().year - 1}-01-01"
            lst = dart.list(info.corp_code, start=start, kind="")  # kind="" → 전 유형
            if lst is not None and len(lst) > 0:
                out: List[dict] = []
                for _, row in lst.head(n).iterrows():
                    rno = str(row.get("rcept_no", "")).strip()
                    raw = str(row.get("rcept_dt", "")).strip()
                    d = f"{raw[:4]}-{raw[4:6]}-{raw[6:]}" if len(raw) == 8 else raw
                    out.append({
                        "title": str(row.get("report_nm", "")).strip(),
                        "date": d,
                        "rcept_no": rno,
                        "url": config.dart_doc_url(rno) if rno else "",
                    })
                if out:
                    return out
        except Exception:
            pass

    # fallback: 내장 샘플(링크 없음)
    return [
        {"title": s["title"], "date": s["date"], "rcept_no": "", "url": ""}
        for s in _SAMPLE_DISCLOSURES.get(info.ticker, [])
    ]


if __name__ == "__main__":
    import sys

    name = sys.argv[1] if len(sys.argv) > 1 else "삼성전자"
    print("resolve:", resolve_corp(name))
    rep = fetch_latest_report(name)
    print("report rcept_no:", rep["rcept_no"] if rep else None)
    print("report chars:", len(rep["text"]) if rep else 0)
    print("event dates:", fetch_event_dates(name)[:5])
