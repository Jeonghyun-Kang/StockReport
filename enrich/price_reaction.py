"""과거 주가 반응: 유사 공시 이후 5거래일 수익률을 수집·집계 (yfinance).

- 저장하지 않고 요청 시점에 계산(선택적 단기 캐시 허용).
- day0 = 이벤트 접수일 당일 또는 직후 첫 거래일 종가, day+5 = 5거래일 후 종가(거래일 인덱싱).
- 표본 부족(n<5) 시 "참고만" 플래그. 과거≠미래 면책은 상위 레이어/프롬프트에서 강제.
- yfinance 불가 시 내장 샘플 분포로 fallback(MVP 시연용, 명시적으로 표시).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Dict, List, Optional

from utils import ensure_root_on_path

ensure_root_on_path()
import config  # noqa: E402


@dataclass
class PriceReaction:
    symbol: str
    n: int
    mean_5d_return: float
    median_5d_return: float
    min_5d_return: float
    max_5d_return: float
    up_ratio: float
    events: List[Dict] = field(default_factory=list)  # [{date, ret_5d}]
    is_sample: bool = False
    insufficient: bool = False
    summary: str = ""


# MVP 내장 샘플(타겟 종목, yfinance 불가 시) — 명시적으로 sample 표시
_SAMPLE_RETURNS = {
    "005930.KS": [0.012, -0.008, 0.021, 0.003, -0.015, 0.018, 0.027, -0.004, 0.009, 0.006, -0.011, 0.014],
    "000660.KQ": [],
    "000660.KS": [0.031, -0.012, 0.045, -0.022, 0.018, 0.026, -0.009, 0.038, 0.011, -0.017],
}


def _compute_event_return(df, event_date: str, window: int) -> Optional[float]:
    """이벤트 일자 기준 day0 종가 → window 거래일 후 종가 수익률."""
    import pandas as pd

    ev = pd.Timestamp(event_date)
    closes = df["Close"]
    # day0: 이벤트 당일 또는 직후 첫 거래일
    after = closes[closes.index >= ev]
    if len(after) < window + 1:
        return None
    base = float(after.iloc[0])
    fut = float(after.iloc[window])
    if base <= 0:
        return None
    return fut / base - 1.0


def _aggregate(symbol: str, rets: List[float], events: List[Dict], is_sample: bool) -> PriceReaction:
    import statistics

    n = len(rets)
    if n == 0:
        return PriceReaction(
            symbol, 0, 0, 0, 0, 0, 0, [], is_sample, True,
            "유사 공시 표본을 확보하지 못해 과거 주가 반응 통계를 제공할 수 없습니다.",
        )
    mean = sum(rets) / n
    median = statistics.median(rets)
    mn, mx = min(rets), max(rets)
    up = sum(1 for r in rets if r > 0)
    up_ratio = up / n
    insufficient = n < config.PRICE_MIN_SAMPLE

    sample_tag = "(내장 샘플) " if is_sample else ""
    warn = " ※ 표본이 적어(n<5) 참고용으로만 활용하세요." if insufficient else ""
    summary = (
        f"{sample_tag}유사 공시 표본 {n}건 · 이후 {config.PRICE_REACTION_WINDOW}거래일 "
        f"평균 {mean*100:+.1f}% (중앙값 {median*100:+.1f}%, 범위 {mn*100:+.1f}%~{mx*100:+.1f}%) · "
        f"상승 {up}/{n}. 과거의 통계적 분포일 뿐 미래 수익을 보장하지 않습니다.{warn}"
    )
    return PriceReaction(
        symbol=symbol, n=n, mean_5d_return=round(mean, 4), median_5d_return=round(median, 4),
        min_5d_return=round(mn, 4), max_5d_return=round(mx, 4), up_ratio=round(up_ratio, 3),
        events=events, is_sample=is_sample, insufficient=insufficient, summary=summary,
    )


@lru_cache(maxsize=32)
def _download(symbol: str, start: str, end: str):
    import yfinance as yf

    return yf.download(symbol, start=start, end=end, auto_adjust=True, progress=False)


def get_price_reaction(
    ticker: str, market: str, event_dates: List[str], window: int = None
) -> PriceReaction:
    window = window or config.PRICE_REACTION_WINDOW
    symbol = config.yf_symbol(ticker, market)
    event_dates = event_dates[: config.PRICE_MAX_EVENTS]

    rets: List[float] = []
    events: List[Dict] = []

    if event_dates:
        try:
            import pandas as pd  # noqa: F401

            lo = min(event_dates)
            hi = (datetime.fromisoformat(max(event_dates)) + timedelta(days=40)).date().isoformat()
            df = _download(symbol, lo, hi)
            if df is not None and len(df) > 0:
                # 멀티인덱스 컬럼 방지
                if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
                    df.columns = df.columns.get_level_values(0)
                for ed in event_dates:
                    r = _compute_event_return(df, ed, window)
                    if r is not None:
                        rets.append(r)
                        events.append({"date": ed, "ret_5d": round(r, 4)})
        except Exception:
            rets, events = [], []

    if rets:
        return _aggregate(symbol, rets, events, is_sample=False)

    # fallback: 내장 샘플
    sample = _SAMPLE_RETURNS.get(symbol) or []
    if sample:
        ev = []
        base = datetime.today()
        for i, r in enumerate(sample):
            d = (base - timedelta(days=90 * (i + 1))).date().isoformat()
            ev.append({"date": d, "ret_5d": round(r, 4)})
        return _aggregate(symbol, sample, ev, is_sample=True)

    return _aggregate(symbol, [], [], is_sample=False)


if __name__ == "__main__":
    pr = get_price_reaction("005930", "KOSPI", [])
    print(pr.summary)
    print("events:", pr.events[:3])
