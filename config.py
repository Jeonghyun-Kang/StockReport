"""중앙 설정: 성향/기간/비중 매핑, 컬렉션명, 시장→yfinance 접미사, 면책 문구."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# 경로
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
KNOWLEDGE_DIR = DATA_DIR / "knowledge"
RAW_REPORTS_DIR = DATA_DIR / "raw_reports"
CORP_MASTER_CSV = DATA_DIR / "corp_master.csv"
STORE_DIR = BASE_DIR / "store"

KNOWLEDGE_DOC = KNOWLEDGE_DIR / "투자제안_지식문서.md"

# ---------------------------------------------------------------------------
# 벡터스토어 (2개로 완전 분리)
# ---------------------------------------------------------------------------
DISCLOSURE_COLLECTION = "disclosure"   # vectorDB #1 (DART 사업보고서)
ADVISORY_COLLECTION = "advisory"       # vectorDB #2 (투자방향 제안 지식)
DISCLOSURE_STORE = STORE_DIR / "disclosure"
ADVISORY_STORE = STORE_DIR / "advisory"

# 청킹 파라미터
CHUNK_SIZE = 800        # 600~1000자
CHUNK_OVERLAP = 100

# ---------------------------------------------------------------------------
# 환경변수
# ---------------------------------------------------------------------------
DART_API_KEY = os.getenv("DART_API_KEY", "")
NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET", "")

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "")

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "jhgan/ko-sroberta-multitask")
EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL", "")
EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY", "")
EMBEDDING_API_MODEL = os.getenv("EMBEDDING_API_MODEL", "")

# ---------------------------------------------------------------------------
# 리스크 성향 (금융투자협회 표준투자권유준칙 → 3단계 압축)
# ---------------------------------------------------------------------------
RISK_PROFILES = ["안정형", "중립형", "공격형"]
DEFAULT_RISK_PROFILE = "중립형"

RISK_PROFILE_GUIDE = {
    "안정형": {
        "fia_mapping": "안정추구형/안정형",
        "tolerated_grades": "낮은 위험(5등급)·매우 낮은 위험(6등급)",
        "principle": (
            "원금 손실 최소화와 안정적 배당·이자 소득을 최우선. 긍정적 공시에도 과도한 비중 "
            "확대는 지양하고, 약간의 불확실성에도 방어적 비중 축소·헷지를 우선 검토."
        ),
    },
    "중립형": {
        "fia_mapping": "위험중립형",
        "tolerated_grades": "다소 높은 위험(3등급)·보통 위험(4등급)",
        "principle": (
            "예·적금 이상 수익을 위해 일정 위험을 감수하나 극단적 변동성은 기피. 공시 이벤트 시 "
            "벤치마크 균형 유지를 위한 기계적 리밸런싱·부분 차익 실현·관망 중심의 중립적 제안."
        ),
    },
    "공격형": {
        "fia_mapping": "공격투자형/적극투자형",
        "tolerated_grades": "매우 높은 위험(1등급)·높은 위험(2등급)",
        "principle": (
            "시장 평균을 크게 상회하는 목표를 지향하며 원금 손실 위험을 적극 수용. 호재 시 모멘텀 "
            "극대화를 위한 공격적 비중 확대, 단기 악재 시 전술적 인내·역발상 매수 검토."
        ),
    },
}

# ---------------------------------------------------------------------------
# 투자 기간
# ---------------------------------------------------------------------------
HORIZONS = ["단기", "중기", "장기"]
DEFAULT_HORIZON = "중기"
HORIZON_GUIDE = {
    "단기": "약 6개월 이내. 단기 모멘텀·변동성에 민감, 트렌드/수급 신호 가중.",
    "중기": "6개월~2년. 실적 추세와 산업 사이클 중심의 균형적 판단.",
    "장기": "2년 이상. 펀더멘털·배당·구조적 성장에 집중, 단기 노이즈 영향 축소.",
}

# ---------------------------------------------------------------------------
# 보유 비중 구간 (자본시장법 제81조 분산투자 10% 기준 차용)
# ---------------------------------------------------------------------------
def weight_bucket(weight: float) -> str:
    """보유 비중(%) → 집중 리스크 구간 라벨."""
    if weight < 10:
        return "10% 미만"
    if weight < 30:
        return "10% 이상 ~ 30% 미만"
    return "30% 이상"


WEIGHT_BUCKET_GUIDE = {
    "10% 미만": {
        "exposure": "낮은 노출도 (Low Exposure)",
        "risk_level": "통제 가능",
        "note": (
            "개별 종목의 극단적 꼬리 위험이 발생해도 전체 포트폴리오 훼손이 10% 이내로 제한되는 "
            "안전 구간. 맹목적 비중 축소보다 자산배분 관점의 여유로운 관망 가능."
        ),
    },
    "10% 이상 ~ 30% 미만": {
        "exposure": "적정·관심 노출도 (Moderate Exposure)",
        "risk_level": "유의 필요",
        "note": (
            "자본시장법상 일반 펀드 동일 종목 한도(10%)를 상회하는 구간. 공시 파급 효과가 "
            "포트폴리오 수익률 궤적을 실질적으로 변화시키므로 성향별 정밀한 비중 조절 검토 필수."
        ),
    },
    "30% 이상": {
        "exposure": "과대 노출도 (Over-Concentrated)",
        "risk_level": "고위험 구간",
        "note": (
            "단일 종목 리스크가 포트폴리오 전체의 생사여탈권을 쥔 극단적 쏠림. 부정적 공시 시 "
            "심각한 원금 손실 위험 → 안정형·중립형에는 비중 축소·분산 가이드를 최우선 인출."
        ),
    },
}

# ---------------------------------------------------------------------------
# 시장 → yfinance 심볼 접미사
# ---------------------------------------------------------------------------
MARKET_SUFFIX = {"KOSPI": ".KS", "KOSDAQ": ".KQ"}


def yf_symbol(ticker: str, market: str) -> str:
    """종목코드 + 시장 → yfinance 심볼 (예: 005930 + KOSPI -> 005930.KS)."""
    suffix = MARKET_SUFFIX.get((market or "KOSPI").upper(), ".KS")
    return f"{ticker}{suffix}"


# ---------------------------------------------------------------------------
# DART 공시 원문 뷰어 링크
# ---------------------------------------------------------------------------
def dart_doc_url(rcept_no: str) -> str:
    """접수번호(rcept_no) → DART 공시 원문 뷰어 URL."""
    return f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"


# ---------------------------------------------------------------------------
# 과거 주가 반응
# ---------------------------------------------------------------------------
PRICE_REACTION_WINDOW = 5     # 이벤트 후 거래일 수
PRICE_MIN_SAMPLE = 5          # 이 미만이면 "표본 부족, 참고만"
PRICE_MAX_EVENTS = 20         # 수집할 과거 이벤트 최대 개수

# ---------------------------------------------------------------------------
# 검색 top-k
# ---------------------------------------------------------------------------
DISCLOSURE_TOP_K = 5
ADVISORY_TOP_K = 3

# ---------------------------------------------------------------------------
# 면책 (항구적 고지)
# ---------------------------------------------------------------------------
DISCLAIMER = (
    "본 제안은 과거 데이터에 기반한 투자 참고용 통계 정보일 뿐이며, 금융투자상품의 매수/매도를 "
    "권유하는 법적 투자자문이 아닙니다. 과거 주가 반응 패턴은 미래의 수익률을 보장하거나 방향성을 "
    "단정하지 않습니다. 최종적인 투자 판단과 그에 따른 모든 책임은 전적으로 사용자 본인에게 있습니다."
)


def ensure_dirs() -> None:
    for d in (DATA_DIR, KNOWLEDGE_DIR, RAW_REPORTS_DIR, DISCLOSURE_STORE, ADVISORY_STORE):
        d.mkdir(parents=True, exist_ok=True)
