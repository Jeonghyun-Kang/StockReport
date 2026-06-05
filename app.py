"""Streamlit 단일 페이지 — 공시 기반 투자 의사결정 참고 리포트.

입력(기업명/보유 비중/성향/기간/관심포인트) → 분석 파이프라인 → 리포트.
리스크 섹션을 긍정 요인보다 먼저/강조 배치. 면책 상시 노출. 입력은 세션 내 1회성 처리(휘발).
"""
from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from utils import ensure_root_on_path

ensure_root_on_path()
import config  # noqa: E402
from diagnostics import run_all  # noqa: E402
from ingest.dart_fetch import resolve_corp  # noqa: E402
from llm.analyzer import analyze  # noqa: E402

st.set_page_config(page_title="공시 기반 투자 참고 리포트", page_icon="📑", layout="centered")

# ---------------------------------------------------------------------------
# 사이드바: 연동 상태 패널 (이번 세션 이슈 → 관측성 고도화)
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("🔌 연동 상태")
    probe = st.button("연결 테스트 실행", use_container_width=True,
                      help="DART/네이버는 무료, LLM은 토큰을 아주 조금 사용합니다.")
    statuses = run_all(probe=probe)
    for s in statuses:
        st.markdown(f"{s.icon} **{s.name}**")
        st.caption(s.detail)
    st.divider()
    st.caption(
        "🟢 라이브 · 🟡 폴백(대체) · 🔴 오류\n\n"
        "키는 `.env`에 입력 후 **앱을 재시작**해야 반영됩니다. "
        "CLI 진단: `python -m healthcheck --probe`"
    )

# ---------------------------------------------------------------------------
# 헤더 + 상시 면책 배너
# ---------------------------------------------------------------------------
st.title("📑 공시 기반 투자 의사결정 참고 리포트")
st.caption(
    "DART 사업보고서(RAG) · 네이버 트렌드/뉴스 · 과거 주가 반응 · 성향별 투자방향 지식을 융합한 "
    "개인화 참고 정보입니다."
)
st.warning(
    "⚠️ 본 서비스는 투자 참고용 통계 정보이며 **법적 투자자문이 아닙니다**. "
    "매수/매도를 권유하지 않으며, 과거 주가 반응은 미래 수익을 보장하지 않습니다. "
    "최종 판단과 책임은 사용자 본인에게 있습니다. (입력 정보는 세션 내에서만 처리되며 저장되지 않습니다.)"
)

# ---------------------------------------------------------------------------
# 입력 영역
# ---------------------------------------------------------------------------
st.subheader("1. 분석 정보 입력")
with st.form("input_form"):
    company = st.text_input("기업명", value="삼성전자", help="예: 삼성전자, SK하이닉스")
    col1, col2 = st.columns(2)
    with col1:
        weight = st.slider("보유 비중 (%)", min_value=0.0, max_value=100.0, value=15.0, step=1.0)
        risk_profile = st.radio("투자 성향", config.RISK_PROFILES, index=1, horizontal=True)
    with col2:
        horizon = st.radio("투자 기간", config.HORIZONS, index=1, horizontal=True)
        focus_raw = st.text_input("관심 포인트 (쉼표 구분)", value="HBM, 배당")
    submitted = st.form_submit_button("분석하기 🚀", use_container_width=True)

if weight > 100:
    st.error("보유 비중은 100%를 초과할 수 없습니다.")

# ---------------------------------------------------------------------------
# 분석 실행
# ---------------------------------------------------------------------------
if submitted and company.strip() and weight <= 100:
    info = resolve_corp(company.strip())
    if info is None:
        st.error(f"'{company}' 종목코드를 찾지 못했습니다. 기업명을 확인해 주세요. (예: 삼성전자)")
        st.stop()

    user_input = {
        "company": info.company,
        "ticker": info.ticker,
        "market": info.market,
        "weight": float(weight),
        "held": weight > 0,
        "risk_profile": risk_profile,
        "horizon": horizon,
        "focus_points": [s.strip() for s in focus_raw.split(",") if s.strip()],
    }

    with st.spinner(
        "공시 RAG · 트렌드 · 과거 주가 반응 · 자문 지식을 분석 중...\n"
        "(처음 분석하는 기업은 사업보고서를 받아 인덱싱하므로 20~40초 걸릴 수 있습니다)"
    ):
        result = analyze(user_input)
    res = result.model_dump()

    st.success(f"분석 완료 — {info.company} ({info.ticker} · {info.market})")

    # LLM 폴백 사유 표면화 (조용한 폴백 금지)
    if res.get("llm_used"):
        st.caption(f"🟢 LLM 분석 사용: {config.LLM_MODEL}")
    else:
        st.warning(f"🟡 {res.get('llm_note', 'LLM 미사용 — 규칙기반 분석으로 표시 중입니다.')}")

    # 입력 요약 칩
    bucket = config.weight_bucket(float(weight))
    st.markdown(
        f"**{risk_profile}** · **{horizon}** · 보유 비중 **{weight:.0f}%** "
        f"(`{bucket}` / {config.WEIGHT_BUCKET_GUIDE[bucket]['risk_level']})"
    )

    st.divider()
    st.subheader("2. 분석 리포트")

    thesis = res.get("investment_thesis", {})
    summary = res.get("company_summary", {})
    sources = res.get("disclosure_sources", [])

    # --- 0. 핵심 투자 판단 한 줄 ---
    if thesis.get("one_line"):
        with st.container(border=True):
            st.markdown("### 🎯 핵심 투자 판단")
            st.markdown(f"#### {thesis.get('one_line','')}")
            if thesis.get("key_question"):
                st.markdown(f"**핵심 질문** — {thesis['key_question']}")
            if thesis.get("overall_stance"):
                st.markdown(f"**전반 스탠스** — `{thesis['overall_stance']}`")

    # --- 📄 근거 공시 (제목 자체가 하이퍼링크) ---
    recents = res.get("recent_disclosures", [])
    base_rno = {s.get("rcept_no") for s in sources}
    if sources or recents:
        with st.container(border=True):
            st.markdown("### 📄 근거 공시")

            # 현재 분석 기반(최신 정기보고서)을 따로 강조
            if sources:
                st.markdown("**🎯 현재 분석 기반 — 최신 정기보고서**")
                for s in sources:
                    if s.get("url"):
                        st.markdown(f"> ### 🔗 [{s['label']}]({s['url']})")
                    else:
                        st.markdown(f"> ### {s['label']} _(내장 샘플 · DART 키 설정 시 원문 연결)_")

            # 최근 공시 목록 (이미지 스타일: 날짜 + 제목 링크)
            if recents:
                st.markdown("**🗂️ 최근 공시 목록**")
                for r in recents:
                    title, d, url = r.get("title", ""), r.get("date", ""), r.get("url", "")
                    is_base = r.get("rcept_no") and r.get("rcept_no") in base_rno
                    badge = " 🎯 *(분석 기반)*" if is_base else ""
                    if url:
                        st.markdown(f"- `{d}` &nbsp; [{title}]({url}){badge}")
                    else:
                        st.markdown(f"- `{d}` &nbsp; {title}{badge}")
                st.caption("제목을 클릭하면 DART 공시 원문으로 이동합니다.")

    # --- 🏢 기업 핵심 요약 ---
    with st.container(border=True):
        st.markdown("### 🏢 기업 핵심 요약")
        rows = [
            ("사업 구조", summary.get("business_structure")),
            ("현재 위치", summary.get("current_position")),
            ("재무 건전성", summary.get("financial_quality")),
            ("성장 동력", summary.get("growth_driver")),
            ("핵심 불확실성", summary.get("main_uncertainty")),
        ]
        for label, val in rows:
            if val:
                st.markdown(f"**{label}** · {val}")

    # --- ⚠️ 리스크 (강조, 긍정 요인보다 먼저 — 자본시장법 가드레일) ---
    with st.container(border=True):
        st.markdown("### ⚠️ 공시 기반 리스크 (우선 확인)")
        for r in res.get("risk_factors", []):
            with st.expander(f"🔴 [{r.get('category','')}] {r.get('title','')}", expanded=True):
                if r.get("evidence"):
                    st.markdown(f"**근거** · {r['evidence']}")
                if r.get("why_it_matters"):
                    st.markdown(f"**왜 중요한가** · {r['why_it_matters']}")
                if r.get("user_impact"):
                    st.markdown(f"**나에게 주는 의미** · {r['user_impact']}")
                if r.get("monitoring_signal"):
                    st.markdown(f"**모니터링 지표** · {r['monitoring_signal']}")

    # --- ✅ 긍정 요인 ---
    with st.container(border=True):
        st.markdown("### ✅ 공시 기반 긍정 요인")
        for p in res.get("positive_factors", []):
            with st.expander(f"🟢 [{p.get('category','')}] {p.get('title','')}", expanded=True):
                if p.get("evidence"):
                    st.markdown(f"**근거** · {p['evidence']}")
                if p.get("why_it_matters"):
                    st.markdown(f"**왜 중요한가** · {p['why_it_matters']}")
                if p.get("investment_implication"):
                    st.markdown(f"**투자 판단상 의미** · {p['investment_implication']}")

    # --- 📈 트렌드 해석 ---
    with st.container(border=True):
        st.markdown("### 📈 최근 트렌드 해석")
        tr = res.get("trend_interpretation", {})
        if tr.get("trend_signal"):
            st.markdown(f"**신호** · {tr['trend_signal']}")
        if tr.get("interpretation"):
            st.markdown(f"**해석** · {tr['interpretation']}")
        st.caption(f"⚠️ {tr.get('caution', '트렌드/뉴스는 관심·변동성 신호일 뿐 호재/악재 방향을 의미하지 않습니다.')}")

    # --- 📊 과거 주가 반응 ---
    with st.container(border=True):
        st.markdown(f"### 📊 과거 주가 반응 (유사 공시 이후 {config.PRICE_REACTION_WINDOW}거래일)")
        pr = res.get("historical_price_reaction", {})
        st.write(pr.get("summary", ""))
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("표본 수", f"{pr.get('n', 0)}건")
        m2.metric("평균 5거래일", f"{pr.get('mean_5d_return', 0)*100:+.1f}%")
        m3.metric("최저", f"{pr.get('min_5d_return', 0)*100:+.1f}%")
        m4.metric("최고", f"{pr.get('max_5d_return', 0)*100:+.1f}%")
        events = pr.get("events", [])
        if events:
            df = pd.DataFrame(events)
            df["ret_5d(%)"] = df["ret_5d"] * 100
            st.bar_chart(df.set_index("date")["ret_5d(%)"])
        if pr.get("how_to_use"):
            st.markdown(f"**활용법** · {pr['how_to_use']}")
        st.caption(f"⚠️ {pr.get('caution', '과거 ≠ 미래: 위 통계는 미래 수익을 보장하지 않습니다.')}")

    # --- 🧭 성향별 투자 방향 (서술형 + 3관점) ---
    with st.container(border=True):
        st.markdown("### 🧭 성향별 투자 방향 (범주형 참고 가이드)")
        g = res.get("personalized_guidance", {})
        if g.get("narrative"):
            st.success(g["narrative"])
        if g.get("recommended_stance"):
            st.markdown(f"**종합 스탠스** · `{g['recommended_stance']}`")
        if g.get("rationale"):
            st.caption(g["rationale"])
        ag = g.get("action_guide", {})
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("**🅰️ 현재 보유자**")
            st.info(ag.get("current_holding", "-"))
        with c2:
            st.markdown("**🅱️ 추가 매수**")
            st.info(ag.get("additional_buying", "-"))
        with c3:
            st.markdown("**🅲 리스크 관리**")
            st.info(ag.get("risk_control", "-"))
        st.caption("구체적 목표가·수량 없이 범주형 가이드만 제공합니다(자본시장법 가드레일).")

    # --- 면책 (하단 고정) ---
    st.divider()
    st.caption(f"📌 {res['disclaimer']}")

    # --- 원본 JSON / 근거 ---
    with st.expander("원본 JSON / 검색 근거 보기"):
        st.json(res)

else:
    st.info("좌측 정보를 입력하고 **분석하기**를 누르면 리포트가 생성됩니다.")
