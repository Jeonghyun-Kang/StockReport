"""입력 + 공시(#1) + 트렌드/뉴스 + 과거 주가 반응 + 자문(#2) → LLM 프롬프트 조립.

개선 가이드(investment_report_improvement_guide.md) 반영:
- 각 긍정/리스크는 단순 나열 금지 → 근거·의미·중요한 이유·사용자 연결·모니터링 지표 포함
- 성향별 방향은 현재 보유자 / 추가 매수 / 리스크 관리 3관점으로 분리
- 기업 요약에 '핵심 투자 질문' 포함, 모니터링 체크리스트·해석 주의점 포함
- 최소 개수 제약 + 금지/권장 표현
"""
from __future__ import annotations

from typing import Dict, List

from utils import ensure_root_on_path

ensure_root_on_path()
import config  # noqa: E402


SYSTEM_PROMPT = """너는 공시 기반 투자 '참고 정보' 분석기다. 다음 규칙을 절대적으로 준수한다.

[근거 제약]
- 제공된 공시 청크 / 트렌드·뉴스 / 과거 주가 반응 / 자문 지식 / 사용자 입력만 근거로 한다.
- 컨텍스트에 없는 수치·사실을 지어내지 마라(할루시네이션 금지). 과거 주가 통계 수치는 제공된 값만 사용한다.

[법적 가드레일 — 자본시장법 / 미등록 투자자문업 차단]
- 직접적인 매수·매도 권유, 구체적 목표가·호가·매수/매도 수량을 절대 명시하지 마라.
- 다음 표현을 금지한다: 무조건 매수, 강력 매수, 반드시 매도, 수익 보장, 목표가, 확실한 상승, 원금 보장.
- 다음 범주형 표현만 사용한다: 보유 유지, 관망, 분할 접근 검토, 비중 확대 신중, 리스크 점검 필요,
  실적 확인 후 판단, 단기 변동성 유의, 모니터링 강화.
- 과거 주가 반응은 미래 수익 예측이 아니라 과거 유사 상황의 분포 참고 자료로만 설명한다.
- 트렌드/뉴스는 호재·악재로 단정하지 말고 관심도·변동성·시장 민감도 신호로만 해석한다.

[분석 깊이 — 매우 중요]
- 각 '긍정 요인'과 '리스크'는 단순 나열 금지. 반드시 다음을 포함하라:
  ① 공시 근거(evidence) ② 그 근거가 의미하는 바·왜 중요한지(why_it_matters)
  ③ 투자 판단상 의미/사용자 성향·보유비중과의 연결 ④ (리스크는) 앞으로 모니터링할 지표(monitoring_signal)
- 기업 핵심 요약은 단순 소개가 아니라 '지금 투자 판단에서 확인해야 할 핵심 질문'을 포함하라.
- 성향별 투자방향의 narrative는 반드시 사용자의 투자 성향·투자 기간·보유 비중 3가지를 모두 문장에 녹여
  2~3문장으로 서술하라. 예: "중립형·중기 투자자로 보유 비중 15%는 유의 구간입니다. 공시 기반 리스크와
  트렌드 하락을 감안하면 추가 매수보다 현 비중 유지가 적절합니다. 배당 수익은 중기 보유 시 유효한 수익원이
  될 수 있습니다." 또한 현재 보유자 / 추가 매수 / 리스크 관리 3관점도 action_guide로 나눠 작성하라.
- 리스크를 긍정 요인보다 충분히, 먼저 제시하라(리스크 우선).

[최소 개수]
- positive_factors ≥ 3, risk_factors ≥ 3.

[출력]
- 아래 JSON 스키마로만 응답한다. 코드펜스(```)나 서문 없이 순수 JSON만 출력한다."""


OUTPUT_SCHEMA_HINT = """{
  "investment_thesis": {
    "one_line": "핵심 투자 판단 한 줄 (이 기업이 지금 무엇을 확인해야 하는 기업인지)",
    "key_question": "현재 투자 판단의 핵심 질문",
    "overall_stance": "전반 스탠스(범주형: 예 '보유 유지 + 추가 매수는 확인 후 판단')"
  },
  "company_summary": {
    "business_structure": "사업 구조",
    "current_position": "현재 기업의 위치(강점/확인 필요 변수)",
    "financial_quality": "재무 건전성 평가",
    "growth_driver": "핵심 성장 동력",
    "main_uncertainty": "핵심 불확실성"
  },
  "positive_factors": [
    {"title": "", "category": "재무 안정성|성장 모멘텀|주주환원|산업 수혜|경쟁력 강화",
     "evidence": "공시 근거", "why_it_matters": "왜 중요한지", "investment_implication": "성향/비중 연결 의미"}
  ],
  "risk_factors": [
    {"title": "", "category": "시장 리스크|사업 리스크|재무 리스크|지배구조|규제",
     "evidence": "공시 근거", "why_it_matters": "의미·중요한 이유",
     "user_impact": "사용자 성향/보유비중과의 연결", "monitoring_signal": "앞으로 볼 지표"}
  ],
  "trend_interpretation": {
    "trend_signal": "관심도 변동 신호(방향 단정 금지)", "interpretation": "해석", "caution": "오독 주의점"
  },
  "historical_price_reaction": {
    "summary": "(제공된 수치 그대로 요약)", "how_to_use": "이 통계를 참고하는 방법", "caution": "과거≠미래 주의"
  },
  "personalized_guidance": {
    "narrative": "투자 성향·투자 기간·보유 비중 3가지를 모두 녹인 2~3문장 서술형 방향",
    "recommended_stance": "범주형 종합 스탠스",
    "rationale": "근거(리스크·긍정 요인·성향·비중 종합)",
    "action_guide": {
      "current_holding": "현재 보유자 관점 가이드(범주형)",
      "additional_buying": "추가 매수 관점 가이드(확인 신호·분할 접근 등)",
      "risk_control": "리스크 관리 관점 가이드(집중도·분산 등)"
    }
  }
}"""


# D1: 병렬 2분할 스키마 (구조는 동일, 호출만 둘로 나눠 동시 생성 → 지연 단축)
SCHEMA_PART_A = """{
  "investment_thesis": {
    "one_line": "핵심 투자 판단 한 줄 (이 기업이 지금 무엇을 확인해야 하는 기업인지)",
    "key_question": "현재 투자 판단의 핵심 질문",
    "overall_stance": "전반 스탠스(범주형)"
  },
  "company_summary": {
    "business_structure": "사업 구조", "current_position": "현재 위치(강점/확인 변수)",
    "financial_quality": "재무 건전성", "growth_driver": "핵심 성장 동력", "main_uncertainty": "핵심 불확실성"
  },
  "positive_factors": [
    {"title": "", "category": "재무 안정성|성장 모멘텀|주주환원|산업 수혜|경쟁력 강화",
     "evidence": "공시 근거", "why_it_matters": "왜 중요한지", "investment_implication": "성향/비중 연결 의미"}
  ],
  "risk_factors": [
    {"title": "", "category": "시장 리스크|사업 리스크|재무 리스크|지배구조|규제",
     "evidence": "공시 근거", "why_it_matters": "의미·중요한 이유",
     "user_impact": "성향/보유비중과의 연결", "monitoring_signal": "앞으로 볼 지표"}
  ]
}"""

SCHEMA_PART_B = """{
  "trend_interpretation": {
    "trend_signal": "관심도 변동 신호(방향 단정 금지)", "interpretation": "해석", "caution": "오독 주의점"
  },
  "historical_price_reaction": {
    "summary": "(제공된 수치 그대로 요약)", "how_to_use": "통계 참고 방법", "caution": "과거≠미래 주의"
  },
  "personalized_guidance": {
    "narrative": "투자 성향·투자 기간·보유 비중 3가지를 모두 녹인 2~3문장 서술형 방향",
    "recommended_stance": "범주형 종합 스탠스",
    "rationale": "근거(리스크·긍정 요인·성향·비중 종합)",
    "action_guide": {
      "current_holding": "현재 보유자 관점(범주형)",
      "additional_buying": "추가 매수 관점(확인 신호·분할 접근)",
      "risk_control": "리스크 관리 관점(집중도·분산)"
    }
  }
}"""


def _fmt_hits(hits, label: str, key: str) -> str:
    if not hits:
        return f"({label} 없음)"
    lines = []
    for i, h in enumerate(hits, 1):
        tag = h.metadata.get(key, "")
        lines.append(f"[{label} {i} · {tag}] {h.text}")
    return "\n".join(lines)


def build_user_prompt(
    user_input: Dict,
    disclosure_hits: List,
    advisory_hits: List,
    trend_content: str,
    price_reaction: Dict,
    schema_hint: str = OUTPUT_SCHEMA_HINT,
) -> str:
    bucket = config.weight_bucket(float(user_input.get("weight", 0)))
    rg = config.RISK_PROFILE_GUIDE.get(user_input["risk_profile"], {})
    wg = config.WEIGHT_BUCKET_GUIDE.get(bucket, {})
    hg = config.HORIZON_GUIDE.get(user_input.get("horizon", config.DEFAULT_HORIZON), "")

    return f"""[사용자 입력]
- 기업명: {user_input['company']} (종목코드 {user_input.get('ticker','?')}, {user_input.get('market','?')})
- 보유 비중: {user_input.get('weight', 0)}% → 구간 '{bucket}' / {wg.get('exposure','')} / 집중리스크 {wg.get('risk_level','')}
- 리스크 성향: {user_input['risk_profile']} ({rg.get('fia_mapping','')}) — {rg.get('principle','')}
- 투자 기간: {user_input.get('horizon','')} — {hg}
- 관심 포인트: {', '.join(user_input.get('focus_points', [])) or '(없음)'}

[보유 비중 구간 함의]
{wg.get('note','')}

[① 공시 RAG — DART 사업보고서 청크 (vectorDB #1)]
{_fmt_hits(disclosure_hits, '공시', 'source')}

[② 실시간 트렌드/뉴스 — 방향성 신호 아님]
{trend_content}

[③ 과거 주가 반응 — 통계 참고, 미래 보장 아님 (이 수치만 사용)]
{price_reaction.get('summary','(데이터 없음)')}
세부: n={price_reaction.get('n',0)}, 평균={price_reaction.get('mean_5d_return',0)}, 범위=[{price_reaction.get('min_5d_return',0)}, {price_reaction.get('max_5d_return',0)}]

[④ 투자방향 제안 지식 — 행동 제안 매트릭스 (vectorDB #2)]
{_fmt_hits(advisory_hits, '자문', 'section')}

위 컨텍스트만 근거로, 아래 스키마의 JSON으로만 응답하라. 각 항목의 깊이 요건과 최소 개수를 반드시 지켜라.
요청된 키만 채우고 다른 키는 만들지 마라.
{schema_hint}"""


def build_query(user_input: Dict) -> str:
    fp = " ".join(user_input.get("focus_points", []))
    return (
        f"{user_input['company']} {fp} 핵심 재무 실적 리스크 "
        f"+ {user_input['risk_profile']} {user_input.get('horizon','')} 판단 기준 행동 제안"
    ).strip()
