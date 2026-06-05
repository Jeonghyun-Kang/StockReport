"""네이버 데이터랩 검색어 트렌드 + 뉴스 검색 실시간 조회 → 자연어 content.

- 저장하지 않고 요청 시점에 조회한다.
- 트렌드는 방향성 신호가 아니다: "정보 민감도·변동성 확대 징후"로만 묘사(trend_note).
- 뉴스는 제목/요약만 사용(본문 전체 복제 금지).
- 키 없거나 실패 시 graceful fallback(중립적 안내 문구).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import List

import requests

from utils import ensure_root_on_path

ensure_root_on_path()
import config  # noqa: E402


@dataclass
class TrendResult:
    keyword: str
    available: bool
    change_pct: float = 0.0          # 최근 1주 vs 직전 4주 평균 대비 (%)
    trend_note: str = ""             # 방향 단정 없는 묘사
    headlines: List[str] = field(default_factory=list)
    content: str = ""                # LLM 프롬프트용 자연어
    series: List[float] = field(default_factory=list)  # 차트용 상대지수 시계열


def _headers() -> dict:
    return {
        "X-Naver-Client-Id": config.NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": config.NAVER_CLIENT_SECRET,
        "Content-Type": "application/json",
    }


def _fetch_trend_series(keyword: str) -> List[float]:
    end = date.today()
    start = end - timedelta(days=120)
    body = {
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "timeUnit": "week",
        "keywordGroups": [{"groupName": keyword, "keywords": [keyword]}],
    }
    resp = requests.post(
        "https://openapi.naver.com/v1/datalab/search",
        headers=_headers(),
        json=body,
        timeout=8,
    )
    resp.raise_for_status()
    data = resp.json()
    pts = data["results"][0]["data"]
    return [float(p["ratio"]) for p in pts]


def _fetch_news(keyword: str, display: int = 5) -> List[str]:
    resp = requests.get(
        "https://openapi.naver.com/v1/search/news.json",
        headers=_headers(),
        params={"query": keyword, "display": display, "sort": "date"},
        timeout=8,
    )
    resp.raise_for_status()
    items = resp.json().get("items", [])
    out = []
    for it in items:
        title = _strip_tags(it.get("title", ""))
        if title:
            out.append(title)
    return out


def _strip_tags(s: str) -> str:
    import re

    return re.sub(r"<[^>]+>", "", s).replace("&quot;", '"').replace("&amp;", "&").strip()


def _change_pct(series: List[float]) -> float:
    """최근 1주(마지막 점) vs 직전 4주 평균 대비 변동률(%)."""
    if len(series) < 5:
        return 0.0
    recent = series[-1]
    prev_avg = sum(series[-5:-1]) / 4.0
    if prev_avg == 0:
        return 0.0
    return (recent - prev_avg) / prev_avg * 100.0


def get_trend_and_news(keyword: str) -> TrendResult:
    if not (config.NAVER_CLIENT_ID and config.NAVER_CLIENT_SECRET):
        note = (
            f"'{keyword}' 네이버 트렌드/뉴스 API 키가 설정되지 않아 실시간 관심도 데이터를 "
            f"수집하지 못했습니다. (트렌드는 방향성 신호가 아니라 정보 민감도·변동성 참고 지표입니다.)"
        )
        return TrendResult(keyword, available=False, trend_note=note, content=note)

    try:
        series = _fetch_trend_series(keyword)
        change = _change_pct(series)
        direction = "상승" if change >= 0 else "하락"
        trend_note = (
            f"최근 1주 '{keyword}' 검색 관심도가 직전 4주 평균 대비 약 {change:+.0f}% {direction}. "
            f"이는 시장 참여자의 정보 민감도·변동성 확대 징후일 뿐 호재/악재 방향을 의미하지 않습니다."
        )
        headlines = _fetch_news(keyword)
        news_block = ""
        if headlines:
            news_block = "최근 뉴스 헤드라인: " + " / ".join(headlines[:5])
        content = trend_note + ("\n" + news_block if news_block else "")
        return TrendResult(
            keyword=keyword,
            available=True,
            change_pct=round(change, 1),
            trend_note=trend_note,
            headlines=headlines,
            content=content,
            series=series,
        )
    except Exception as e:  # 네트워크/쿼터 등
        note = (
            f"'{keyword}' 트렌드/뉴스 조회 중 오류로 실시간 데이터를 가져오지 못했습니다 "
            f"({type(e).__name__}). 관심도는 방향성 신호가 아닌 참고 지표입니다."
        )
        return TrendResult(keyword, available=False, trend_note=note, content=note)


if __name__ == "__main__":
    import sys

    r = get_trend_and_news(sys.argv[1] if len(sys.argv) > 1 else "삼성전자")
    print(r.content)
