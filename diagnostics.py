"""연동 상태 진단 + 에러 해석. 이번 세션에서 겪은 이슈들을 자동으로 표면화한다.

- OpenAI 401(키 무효) vs 429(크레딧 부족)를 한국어로 구분 해석
- OpenDartReader 0.3.x import / 키 유무 확인
- 네이버/임베딩 백엔드 확인
- probe=False: 가벼운 점검(설정·import만), probe=True: 실제 1회 호출까지
"""
from __future__ import annotations

from dataclasses import dataclass

from utils import ensure_root_on_path

ensure_root_on_path()
import config  # noqa: E402


@dataclass
class IntegrationStatus:
    name: str
    level: str          # "live" | "fallback" | "error"
    detail: str

    @property
    def icon(self) -> str:
        return {"live": "🟢", "fallback": "🟡", "error": "🔴"}.get(self.level, "⚪")


# ---------------------------------------------------------------------------
# OpenAI 에러 해석 (401 vs 429 vs ...)
# ---------------------------------------------------------------------------
def decode_openai_error(e: Exception) -> str:
    s = str(e)
    low = s.lower()
    if "401" in s or "incorrect api key" in low or "invalid_api_key" in low:
        return "401 인증 실패 — API 키가 올바르지 않습니다(무효·철회·오타). 새 키 발급이 필요합니다."
    if "429" in s or "insufficient_quota" in low or "exceeded your current quota" in low:
        return "429 크레딧/쿼터 부족 — Billing에서 크레딧 충전이 필요합니다(키는 정상)."
    if "rate limit" in low:
        return "429 요청 한도 초과 — 잠시 후 재시도하세요."
    if "403" in s:
        return "403 접근 거부 — 모델/지역 권한을 확인하세요."
    if "model" in low and ("not found" in low or "does not exist" in low):
        return f"모델 미존재 — LLM_MODEL='{config.LLM_MODEL}' 값을 확인하세요."
    return f"{type(e).__name__}: {s[:160]}"


# ---------------------------------------------------------------------------
# 개별 점검
# ---------------------------------------------------------------------------
def check_llm(probe: bool = False) -> IntegrationStatus:
    if not (config.LLM_BASE_URL and config.LLM_API_KEY and config.LLM_MODEL):
        return IntegrationStatus("LLM", "fallback", "키/모델 미설정 — 규칙기반 분석으로 동작합니다.")
    try:
        import openai  # noqa: F401
    except Exception:
        return IntegrationStatus("LLM", "fallback", "openai 패키지 미설치 — `pip install openai`.")
    if not probe:
        return IntegrationStatus("LLM", "live", f"설정됨 ({config.LLM_MODEL}). '연결 테스트'로 실제 확인.")
    try:
        from openai import OpenAI

        c = OpenAI(base_url=config.LLM_BASE_URL, api_key=config.LLM_API_KEY)
        c.chat.completions.create(
            model=config.LLM_MODEL,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
            temperature=0,
        )
        return IntegrationStatus("LLM", "live", f"정상 호출 확인 ({config.LLM_MODEL}).")
    except Exception as e:
        return IntegrationStatus("LLM", "error", decode_openai_error(e))


def check_dart(probe: bool = False) -> IntegrationStatus:
    if not config.DART_API_KEY:
        return IntegrationStatus("DART 공시", "fallback", "DART_API_KEY 미설정 — 내장 샘플 보고서만 사용.")
    try:
        from ingest.dart_fetch import _get_dart
    except Exception as e:
        return IntegrationStatus("DART 공시", "error", f"모듈 로드 실패: {type(e).__name__}")
    if not probe:
        return IntegrationStatus("DART 공시", "live", "키 설정됨. '연결 테스트'로 실제 확인.")
    try:
        dart = _get_dart()
        if dart is None:
            return IntegrationStatus(
                "DART 공시", "error",
                "OpenDartReader 초기화 실패 — 설치/키 확인(`from opendartreader import OpenDartReader`).",
            )
        code = dart.find_corp_code("삼성전자")
        if code:
            return IntegrationStatus("DART 공시", "live", f"정상 (삼성전자 corp_code={code}).")
        return IntegrationStatus("DART 공시", "error", "corp_code 조회 실패 — 키 권한 확인.")
    except Exception as e:
        return IntegrationStatus("DART 공시", "error", f"{type(e).__name__}: {str(e)[:140]}")


def check_naver(probe: bool = False) -> IntegrationStatus:
    if not (config.NAVER_CLIENT_ID and config.NAVER_CLIENT_SECRET):
        return IntegrationStatus("네이버 트렌드/뉴스", "fallback", "키 미설정 — 중립 안내문구로 대체.")
    if not probe:
        return IntegrationStatus("네이버 트렌드/뉴스", "live", "키 설정됨. '연결 테스트'로 실제 확인.")
    try:
        from enrich.naver_trend import get_trend_and_news

        t = get_trend_and_news("삼성전자")
        if t.available:
            return IntegrationStatus("네이버 트렌드/뉴스", "live", "정상 (트렌드+뉴스 수신).")
        return IntegrationStatus("네이버 트렌드/뉴스", "error", t.trend_note[:140])
    except Exception as e:
        return IntegrationStatus("네이버 트렌드/뉴스", "error", f"{type(e).__name__}: {str(e)[:140]}")


def check_embedding(probe: bool = False) -> IntegrationStatus:
    try:
        from embeddings import get_embedder

        emb = get_embedder()
        name = emb.name
        is_tfidf = name.startswith("tfidf")
        level = "fallback" if is_tfidf else "live"
        note = "TF-IDF 폴백(의미검색 제한) — `pip install sentence-transformers` 권장." if is_tfidf else f"{name}"
        if not probe:
            return IntegrationStatus("임베딩", level, note)
        emb_fit = emb
        if getattr(emb, "requires_fit", False):
            emb_fit.fit(["테스트 문장", "임베딩 점검"])
        vec = emb_fit.encode(["임베딩 점검"])
        return IntegrationStatus("임베딩", level, f"{note} (dim={vec.shape[1]})")
    except Exception as e:
        return IntegrationStatus("임베딩", "error", f"{type(e).__name__}: {str(e)[:140]}")


def check_indexes() -> IntegrationStatus:
    """두 벡터스토어 빌드 여부."""
    from vectorstore import LocalVectorStore

    d = LocalVectorStore(config.DISCLOSURE_STORE, config.DISCLOSURE_COLLECTION).exists()
    a = LocalVectorStore(config.ADVISORY_STORE, config.ADVISORY_COLLECTION).exists()
    if d and a:
        return IntegrationStatus("벡터 인덱스", "live", "disclosure + advisory 빌드됨.")
    missing = [n for n, ok in [("disclosure", d), ("advisory", a)] if not ok]
    return IntegrationStatus(
        "벡터 인덱스", "error",
        f"미빌드: {', '.join(missing)} — `python -m ingest.build_*_index` 실행 필요.",
    )


def run_all(probe: bool = False) -> list[IntegrationStatus]:
    return [
        check_indexes(),
        check_embedding(probe),
        check_dart(probe),
        check_naver(probe),
        check_llm(probe),
    ]
