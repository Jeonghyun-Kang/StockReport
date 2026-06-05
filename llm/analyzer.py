"""LLM 호출 → JSON 파싱 → pydantic 검증 → 1회 재시도. LLM 미설정 시 규칙기반 fallback.

개선 가이드 반영: 심화된 중첩 스키마(thesis/요약/요인/리스크/3관점 가이드/체크리스트/주의점) +
공시 원문 링크(disclosure_sources). 전체 파이프라인 오케스트레이션(analyze)도 여기에 둔다.
"""
from __future__ import annotations

import json
import re
from typing import Dict, List

from pydantic import BaseModel, Field, ValidationError

from utils import ensure_root_on_path

ensure_root_on_path()
import config  # noqa: E402
from llm.prompt_builder import SYSTEM_PROMPT, build_query, build_user_prompt  # noqa: E402


# ---------------------------------------------------------------------------
# 출력 스키마 (심화)
# ---------------------------------------------------------------------------
class ThesisModel(BaseModel):
    one_line: str = ""
    key_question: str = ""
    overall_stance: str = ""


class CompanySummaryModel(BaseModel):
    business_structure: str = ""
    current_position: str = ""
    financial_quality: str = ""
    growth_driver: str = ""
    main_uncertainty: str = ""


class PositiveFactor(BaseModel):
    title: str = ""
    category: str = ""
    evidence: str = ""
    why_it_matters: str = ""
    investment_implication: str = ""


class RiskFactor(BaseModel):
    title: str = ""
    category: str = ""
    evidence: str = ""
    why_it_matters: str = ""
    user_impact: str = ""
    monitoring_signal: str = ""


class TrendModel(BaseModel):
    trend_signal: str = ""
    interpretation: str = ""
    caution: str = ""


class HistPriceModel(BaseModel):
    summary: str = ""
    how_to_use: str = ""
    caution: str = ""
    n: int = 0
    mean_5d_return: float = 0.0
    min_5d_return: float = 0.0
    max_5d_return: float = 0.0
    events: List[Dict] = Field(default_factory=list)


class ActionGuideModel(BaseModel):
    current_holding: str = ""
    additional_buying: str = ""
    risk_control: str = ""


class GuidanceModel(BaseModel):
    # 성향·기간·비중을 모두 녹인 2~3문장 서술형 방향(메인)
    narrative: str = ""
    recommended_stance: str = ""
    rationale: str = ""
    action_guide: ActionGuideModel = Field(default_factory=ActionGuideModel)


class DisclosureSource(BaseModel):
    label: str = ""
    rcept_no: str = ""
    date: str = ""
    url: str = ""
    is_sample: bool = False


class RecentDisclosure(BaseModel):
    title: str = ""
    date: str = ""
    rcept_no: str = ""
    url: str = ""


class AnalysisResult(BaseModel):
    company: str
    weight: float = 0.0
    risk_profile: str
    horizon: str = config.DEFAULT_HORIZON
    investment_thesis: ThesisModel = Field(default_factory=ThesisModel)
    company_summary: CompanySummaryModel = Field(default_factory=CompanySummaryModel)
    positive_factors: List[PositiveFactor] = Field(default_factory=list)
    risk_factors: List[RiskFactor] = Field(default_factory=list)
    trend_interpretation: TrendModel = Field(default_factory=TrendModel)
    historical_price_reaction: HistPriceModel = Field(default_factory=HistPriceModel)
    personalized_guidance: GuidanceModel = Field(default_factory=GuidanceModel)
    disclosure_sources: List[DisclosureSource] = Field(default_factory=list)
    recent_disclosures: List[RecentDisclosure] = Field(default_factory=list)
    disclaimer: str = config.DISCLAIMER
    # 관측성
    llm_used: bool = True
    llm_note: str = ""


# ---------------------------------------------------------------------------
# LLM 호출
# ---------------------------------------------------------------------------
def _llm_available() -> bool:
    return bool(config.LLM_BASE_URL and config.LLM_API_KEY and config.LLM_MODEL)


def _strip_code_fence(s: str) -> str:
    s = s.strip()
    s = re.sub(r"^```(?:json)?\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    return s.strip()


def _call_llm(user_prompt: str) -> str:
    from openai import OpenAI

    client = OpenAI(base_url=config.LLM_BASE_URL, api_key=config.LLM_API_KEY)
    resp = client.chat.completions.create(
        model=config.LLM_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
        response_format={"type": "json_object"},
    )
    return resp.choices[0].message.content or ""


def _parse(raw: str) -> "dict | None":
    try:
        return json.loads(_strip_code_fence(raw))
    except Exception:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
        return None


# ---------------------------------------------------------------------------
# 공시 출처 링크 구성 (disclosure_hits 메타데이터 → DART 원문 링크)
# ---------------------------------------------------------------------------
def build_disclosure_sources(disclosure_hits) -> List[DisclosureSource]:
    seen: Dict[str, DisclosureSource] = {}
    for h in disclosure_hits or []:
        rno = str(h.metadata.get("rcept_no", "")).strip()
        if not rno or rno in seen:
            continue
        company = h.metadata.get("company", "")
        is_sample = rno.upper().startswith("SAMPLE")
        date = ""
        if not is_sample and len(rno) >= 8 and rno[:8].isdigit():
            date = f"{rno[:4]}-{rno[4:6]}-{rno[6:8]}"
        label = f"{company} 정기보고서" + (f" ({date})" if date else " (내장 샘플)")
        seen[rno] = DisclosureSource(
            label=label,
            rcept_no=rno,
            date=date,
            url="" if is_sample else config.dart_doc_url(rno),
            is_sample=is_sample,
        )
    return list(seen.values())


# ---------------------------------------------------------------------------
# 규칙기반 fallback (LLM 미설정/실패 시에도 데모 가능)
# ---------------------------------------------------------------------------
def _rule_based(
    user_input: Dict, disclosure_hits, advisory_hits, trend_content: str, price_reaction: Dict,
    note: str = "LLM 미설정 — 규칙기반 분석으로 표시 중입니다.",
) -> AnalysisResult:
    company = user_input["company"]
    weight = float(user_input.get("weight", 0))
    bucket = config.weight_bucket(weight)
    profile = user_input["risk_profile"]
    horizon = user_input.get("horizon", config.DEFAULT_HORIZON)
    wg = config.WEIGHT_BUCKET_GUIDE[bucket]
    focus = ", ".join(user_input.get("focus_points", [])) or "핵심 사업"

    disc_snip = disclosure_hits[0].text[:160] if disclosure_hits else "공시 청크가 없습니다."

    thesis = ThesisModel(
        one_line=f"{company}는 공시상 재무 안정성을 갖추되 {focus} 관련 실적 연결 여부가 {horizon} 판단의 핵심인 기업입니다.",
        key_question=f"공시에서 확인된 {focus} 모멘텀이 실제 실적 개선으로 이어질 수 있는가?",
        overall_stance=_matrix_stance(profile, bucket),
    )
    company_summary = CompanySummaryModel(
        business_structure=f"공시 근거: {disc_snip}",
        current_position=f"보유 비중 {weight:.0f}%는 '{bucket}'({wg['exposure']}) 구간으로 {wg['risk_level']} 상태입니다.",
        financial_quality="사업보고서의 재무 건전성 항목(부채비율·현금흐름)을 우선 확인하세요.",
        growth_driver=f"{focus} 등 관심 포인트 관련 성장 동력은 공시 RAG 청크를 참고하세요.",
        main_uncertainty="업황 변동성·경쟁 심화 등 사업보고서 위험 요인을 확인하세요.",
    )
    positives = [
        PositiveFactor(title="재무 안정성", category="재무 안정성", evidence="사업보고서 재무 항목 (공시 RAG)",
                       why_it_matters="업황 변동이 커도 재무 부담이 낮으면 투자 지속 여력이 큽니다.",
                       investment_implication=f"{profile} 투자자에게 하방 방어 요인으로 해석될 수 있습니다."),
        PositiveFactor(title="주주환원", category="주주환원", evidence="배당/자사주 관련 공시 (공시 RAG)",
                       why_it_matters="보유 기간 중 현금흐름 기대를 제공합니다.",
                       investment_implication=f"{horizon} 보유자에게 단기 변동성을 일부 완충합니다."),
        PositiveFactor(title=f"{focus} 모멘텀", category="성장 모멘텀", evidence="관심 포인트 관련 공시 (공시 RAG)",
                       why_it_matters="산업 수혜 국면에서 밸류에이션 재평가 요인이 될 수 있습니다.",
                       investment_implication="공격형엔 기대 요인, 중립·안정형은 실적 연결 확인이 필요합니다."),
    ]
    risks = [
        RiskFactor(title="시장 변동성", category="시장 리스크", evidence="주가/환율 민감도 (공시 RAG)",
                   why_it_matters="대형주라도 외부 변수로 단기 평가손익 변동성이 커질 수 있습니다.",
                   user_impact=f"{profile}·{horizon}에는 추가 매수보다 변동성 모니터링이 우선입니다.",
                   monitoring_signal="환율, 외국인 순매수, 업황 지표"),
        RiskFactor(title="집중 리스크", category="재무 리스크", evidence=f"보유 비중 {weight:.0f}% / {bucket}",
                   why_it_matters=wg["note"],
                   user_impact="비중이 30%에 가까울수록 단일 종목 집중 리스크가 커집니다. (자본시장법 제81조)",
                   monitoring_signal="포트폴리오 내 업종 분산도, 단일 종목 비중"),
        RiskFactor(title=f"{focus} 경쟁력 회복 지연", category="사업 리스크", evidence="관심 포인트 관련 공시 (공시 RAG)",
                   why_it_matters="수요가 늘어도 경쟁력이 뒤처지면 성장 모멘텀 반영이 제한될 수 있습니다.",
                   user_impact="공격형은 기대감 진입 가능하나, 안정형은 실적 확인 전 보수적 접근이 필요합니다.",
                   monitoring_signal="수주/계약, 고객사 인증, 제품 ASP 회복"),
    ]
    trend = TrendModel(
        trend_signal=trend_content[:200],
        interpretation="검색 관심도는 정보 민감도·변동성 신호이며 매수/매도 방향을 의미하지 않습니다.",
        caution="검색량 변화만으로 호재/악재를 단정하지 마세요.",
    )
    direction = _matrix_direction(profile, bucket)
    narrative = _matrix_narrative(profile, horizon, weight, bucket, focus)
    guidance = GuidanceModel(
        narrative=narrative,
        recommended_stance=_matrix_stance(profile, bucket),
        rationale=f"{profile}·{horizon}·비중 {weight:.0f}%({bucket}) 기준의 범주형 가이드입니다. {direction}",
        action_guide=ActionGuideModel(
            current_holding="현재 비중은 유지하되, 단기 변동성 시 손익보다 공시·실적 변화 여부를 우선 확인하세요.",
            additional_buying="추가 매수는 실적 개선·관심 포인트 관련 확인 신호가 나올 때 분할 접근을 검토하세요.",
            risk_control=f"비중이 30%에 근접하면 집중 리스크가 커지므로 업종 분산을 고려하세요. ({bucket})",
        ),
    )

    return AnalysisResult(
        company=company, weight=weight, risk_profile=profile, horizon=horizon,
        investment_thesis=thesis, company_summary=company_summary,
        positive_factors=positives, risk_factors=risks, trend_interpretation=trend,
        historical_price_reaction=_hist_from_real(price_reaction),
        personalized_guidance=guidance,
        disclaimer=config.DISCLAIMER, llm_used=False, llm_note=note,
    )


def _hist_from_real(pr: Dict) -> HistPriceModel:
    return HistPriceModel(
        summary=pr.get("summary", ""),
        how_to_use="과거 유사 공시 이후 단기 분포의 참고 자료로만 활용하세요(표본 수·범위 함께 고려).",
        caution="과거 ≠ 미래. 위 통계는 미래 수익을 보장하거나 방향을 단정하지 않습니다.",
        n=pr.get("n", 0), mean_5d_return=pr.get("mean_5d_return", 0.0),
        min_5d_return=pr.get("min_5d_return", 0.0), max_5d_return=pr.get("max_5d_return", 0.0),
        events=pr.get("events", []),
    )


def _matrix_stance(profile: str, bucket: str) -> str:
    return {
        ("안정형", "10% 미만"): "보유 유지 + 추가 확대 신중",
        ("안정형", "10% 이상 ~ 30% 미만"): "방어력 점검 + 비중 조정 검토",
        ("안정형", "30% 이상"): "비중 분산·축소 우선 검토",
        ("중립형", "10% 미만"): "관망 + 점진 확대 검토",
        ("중립형", "10% 이상 ~ 30% 미만"): "보유 유지 + 추가 매수는 확인 후 판단",
        ("중립형", "30% 이상"): "부분 차익 실현·리밸런싱 검토",
        ("공격형", "10% 미만"): "전략적 비중 확대 검토",
        ("공격형", "10% 이상 ~ 30% 미만"): "모멘텀 시 홀딩/확대, 단기 변동성 인내 검토",
        ("공격형", "30% 이상"): "초과수익 구간 — 과열 시 단계적 차익 실현 병행",
    }.get((profile, bucket), "리스크 점검 필요 + 관망")


def _matrix_direction(profile: str, bucket: str) -> str:
    return {
        ("안정형", "10% 미만"): "현 비중 안정적 유지·관망. 추가 리스크 확산 시 보수적 일부 축소 검토.",
        ("안정형", "10% 이상 ~ 30% 미만"): "방어력 점검. 리스크 상승 시 현금·보수 자산으로의 비중 조정 적극 검토.",
        ("안정형", "30% 이상"): "분산투자 원칙 위배 구간. 비중 분산·축소 리밸런싱 우선 검토.",
        ("중립형", "10% 미만"): "벤치마크 비중까지 소폭 점진 확대 또는 관망(Hold) 중심.",
        ("중립형", "10% 이상 ~ 30% 미만"): "적정 비중 유지·장기 가치 추종. 무리한 매매 지양.",
        ("중립형", "30% 이상"): "쏠림 완화 위한 부분 차익 실현·리밸런싱으로 적정 비중 복귀 검토.",
        ("공격형", "10% 미만"): "리스크 수용 철학상 전략적 비중 확대 또는 저가 매수 기회 검토 가능.",
        ("공격형", "10% 이상 ~ 30% 미만"): "모멘텀 지속 시 홀딩·확대, 단기 변동성은 전술적 인내 검토.",
        ("공격형", "30% 이상"): "초과수익 구간이나 과열 징후 시 단계적 차익 실현 병행. 치명적 악재 시 과감한 축소·스위칭 검토.",
    }.get((profile, bucket), "성향·비중 매트릭스 기준 범주형 방향을 참고하세요.")


def _matrix_narrative(profile: str, horizon: str, weight: float, bucket: str, focus: str) -> str:
    """성향·기간·비중을 모두 녹인 2~3문장 서술형 방향(규칙기반 fallback용)."""
    level = {"통제 가능": "통제 가능한", "유의 필요": "유의가 필요한", "고위험 구간": "고위험"}.get(
        config.WEIGHT_BUCKET_GUIDE[bucket]["risk_level"], "주의가 필요한"
    )
    s1 = f"{profile}·{horizon} 투자자로 보유 비중 {weight:.0f}%는 {level} 구간입니다."
    s2 = {
        ("안정형", "10% 미만"): "공시 기반 리스크와 트렌드 변화를 감안하면 현 비중을 안정적으로 유지하며 관망하는 것이 적절합니다.",
        ("안정형", "10% 이상 ~ 30% 미만"): "공시 기반 리스크와 트렌드 변화를 감안하면 추가 매수보다 비중 일부 조정과 방어력 점검이 적절합니다.",
        ("안정형", "30% 이상"): "공시 기반 리스크를 감안하면 안정형 철학상 비중 분산·축소를 우선 검토하는 것이 적절합니다.",
        ("중립형", "10% 미만"): "공시 기반 리스크와 트렌드 변화를 감안하면 급한 매매보다 관망하며 점진적 접근을 검토하는 것이 적절합니다.",
        ("중립형", "10% 이상 ~ 30% 미만"): "공시 기반 리스크와 트렌드 하락을 감안하면 추가 매수보다 현 비중 유지가 적절합니다.",
        ("중립형", "30% 이상"): "공시 기반 리스크를 감안하면 쏠림 완화를 위한 부분 차익 실현·리밸런싱을 검토하는 것이 적절합니다.",
        ("공격형", "10% 미만"): "리스크를 적극 수용하는 성향을 감안하면 확인되는 모멘텀에 한해 전략적 비중 확대를 검토할 수 있습니다.",
        ("공격형", "10% 이상 ~ 30% 미만"): "모멘텀이 유지되는 한 홀딩하되 단기 변동성은 전술적으로 인내하는 접근이 가능합니다.",
        ("공격형", "30% 이상"): "초과수익 구간이나 과열 징후가 보이면 단계적 차익 실현을 병행하는 것이 적절합니다.",
    }.get((profile, bucket), "공시 기반 리스크와 트렌드 변화를 감안한 범주형 대응이 적절합니다.")
    s3 = {
        "단기": "단기 구간에서는 단기 변동성 확대에 유의하며 모니터링을 강화하는 것이 바람직합니다.",
        "중기": "배당 수익은 중기 보유 시 유효한 수익원이 될 수 있습니다.",
        "장기": "장기적으로는 단기 노이즈보다 펀더멘털·배당 등 구조적 요인에 집중하는 것이 바람직합니다.",
    }.get(horizon, "")
    return f"{s1} {s2} {s3}".strip()


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------
def run_llm(
    user_input: Dict, disclosure_hits, advisory_hits, trend_content: str, price_reaction: Dict
) -> AnalysisResult:
    """LLM 호출(가능 시) → 검증/재시도, 실패 시 규칙기반 fallback(사유 표면화)."""
    from diagnostics import decode_openai_error

    if not _llm_available():
        return _rule_based(
            user_input, disclosure_hits, advisory_hits, trend_content, price_reaction,
            note="LLM 키/모델 미설정 — 규칙기반 분석으로 표시 중입니다. (.env의 LLM_* 설정)",
        )

    user_prompt = build_user_prompt(
        user_input, disclosure_hits, advisory_hits, trend_content, price_reaction
    )
    last_error = "응답 파싱 실패 — JSON 형식이 아니었습니다."
    for attempt in range(2):
        try:
            raw = _call_llm(user_prompt)
            data = _parse(raw)
            if data is None:
                continue
            data.setdefault("company", user_input["company"])
            data.setdefault("risk_profile", user_input["risk_profile"])
            data.setdefault("weight", user_input.get("weight", 0))
            data.setdefault("horizon", user_input.get("horizon", config.DEFAULT_HORIZON))
            data.setdefault("disclaimer", config.DISCLAIMER)
            # 과거 주가 통계는 실제 계산값으로 강제 덮어쓰기(LLM 환각 방지), 텍스트는 LLM 것 유지
            hp = data.get("historical_price_reaction") or {}
            hp.update({
                "summary": price_reaction.get("summary", hp.get("summary", "")),
                "n": price_reaction.get("n", 0),
                "mean_5d_return": price_reaction.get("mean_5d_return", 0.0),
                "min_5d_return": price_reaction.get("min_5d_return", 0.0),
                "max_5d_return": price_reaction.get("max_5d_return", 0.0),
                "events": price_reaction.get("events", []),
            })
            hp.setdefault("how_to_use", "과거 유사 공시 이후 단기 분포의 참고 자료로만 활용하세요.")
            hp.setdefault("caution", "과거 ≠ 미래. 미래 수익을 보장하지 않습니다.")
            data["historical_price_reaction"] = hp
            data["llm_used"] = True
            data["llm_note"] = ""
            return AnalysisResult(**data)
        except ValidationError as e:
            last_error = f"LLM 응답 검증 실패: {str(e)[:120]}"
        except Exception as e:
            last_error = decode_openai_error(e)
            if "401" in last_error or "429" in last_error or "403" in last_error:
                break
    return _rule_based(
        user_input, disclosure_hits, advisory_hits, trend_content, price_reaction,
        note=f"LLM 호출 실패로 규칙기반 분석으로 표시 중입니다 — {last_error}",
    )


def analyze(user_input: Dict) -> AnalysisResult:
    """전체 파이프라인 오케스트레이션: #1 → 트렌드 → 주가반응 → #2 → LLM → 공시링크."""
    from retrieval.disclosure_retriever import search as disc_search
    from retrieval.advisory_retriever import search as adv_search
    from enrich.naver_trend import get_trend_and_news
    from enrich.price_reaction import get_price_reaction
    from ingest.dart_fetch import fetch_event_dates

    query = build_query(user_input)

    # 인덱스에 없는 기업이면 온디맨드로 사업보고서를 받아 인덱싱
    try:
        from ingest.build_disclosure_index import ensure_indexed

        if ensure_indexed(user_input["company"], user_input.get("ticker")):
            import retrieval.disclosure_retriever as _dr

            _dr._store.cache_clear()  # 새 문서 반영 위해 캐시 무효화
    except Exception:
        pass

    try:
        disclosure_hits = disc_search(query, ticker=user_input.get("ticker"))
    except Exception:
        disclosure_hits = []

    trend = get_trend_and_news(user_input["company"])

    try:
        event_dates = fetch_event_dates(user_input["company"])
    except Exception:
        event_dates = []
    pr = get_price_reaction(user_input.get("ticker", ""), user_input.get("market", "KOSPI"), event_dates)
    price_reaction = {
        "summary": pr.summary, "n": pr.n, "mean_5d_return": pr.mean_5d_return,
        "min_5d_return": pr.min_5d_return, "max_5d_return": pr.max_5d_return, "events": pr.events,
    }

    try:
        advisory_hits = adv_search(query)
    except Exception:
        advisory_hits = []

    result = run_llm(user_input, disclosure_hits, advisory_hits, trend.content, price_reaction)
    result.disclosure_sources = build_disclosure_sources(disclosure_hits)

    # 최근 공시 목록(전 유형) — UI 링크용
    from ingest.dart_fetch import fetch_recent_disclosures

    try:
        recents = fetch_recent_disclosures(user_input["company"])
    except Exception:
        recents = []
    result.recent_disclosures = [RecentDisclosure(**r) for r in recents]
    return result


if __name__ == "__main__":
    sample = {
        "company": "삼성전자", "ticker": "005930", "market": "KOSPI",
        "weight": 15.0, "risk_profile": "중립형", "horizon": "중기",
        "focus_points": ["HBM", "배당"],
    }
    res = analyze(sample)
    print(json.dumps(res.model_dump(), ensure_ascii=False, indent=2))
