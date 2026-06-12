"""살까말까 — 공시 기반 투자 의사결정 참고 리포트 (Streamlit 멀티페이지).

페이지 분리:
  - 분석 페이지: 입력 → 분석 실행 → "분석 완료" 안내 + [리포트 보기] 하이퍼링크
  - 리포트 페이지: 세션에 저장된 분석 결과를 렌더 (재분석 없음)
입력은 세션 내 1회성 처리(휘발), 면책 상시 노출, 리스크 우선 배치.
"""
from __future__ import annotations

import html as _html

import streamlit as st

from utils import ensure_root_on_path

ensure_root_on_path()
import config  # noqa: E402
from diagnostics import run_all  # noqa: E402
from ingest.dart_fetch import resolve_corp  # noqa: E402
from llm.analyzer import analyze  # noqa: E402

st.set_page_config(page_title="살까말까", layout="centered")


def esc(t) -> str:
    return _html.escape(str(t if t is not None else "")).strip()


def H(markup: str) -> None:
    st.markdown(markup, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# 디자인 시스템 (CSS) — 공통(두 페이지에 적용)
# ---------------------------------------------------------------------------
H(
    """
<style>
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css');

:root{
  --blue:#3182F6; --blue-d:#1B64DA; --blue-soft:#F0F6FF;
  --ink:#17171C; --ink2:#4B515B; --ink3:#9098A1;
  --line:#EEF0F3; --line2:#F6F7F9; --paper:#FFFFFF;
  --up:#F0454C; --down:#3182F6;
}
html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stSidebar"], [class*="css"]{
  font-family:'Pretendard', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
  -webkit-font-smoothing:antialiased;
}
.stApp{ background:var(--paper); }
.block-container{ max-width:720px; padding-top:2.4rem; padding-bottom:5rem; }
#MainMenu, header[data-testid="stHeader"], footer{ visibility:hidden; }
p, li, span, label, div[data-testid="stMarkdownContainer"]{ color:var(--ink2); line-height:1.62; }

/* 상단 / 로고 워드마크 */
.masthead{ margin-bottom:6px; }
.logo-word{ display:inline-flex; align-items:baseline; font-weight:800; letter-spacing:-.05em;
  line-height:1; margin-bottom:12px; }
.logo-word .lg{ font-size:2.5rem; } .logo-word .sm{ font-size:1.5rem; }
.logo-word .b{ color:var(--blue); } .logo-word .k{ color:var(--ink); }
.logo-word .q{ font-size:2.3rem; color:var(--blue); display:inline-block;
  transform:rotate(20deg); transform-origin:60% 70%; margin-left:5px; }
.masthead .sub{ font-size:.9rem; color:var(--ink3); line-height:1.55; }
.disclaimer-note{ margin:18px 0 6px; padding:13px 16px; border:1px solid var(--line);
  border-radius:12px; background:var(--line2); font-size:.8rem; color:var(--ink3); line-height:1.6; }

.section-label{ font-size:12px; font-weight:800; letter-spacing:.02em; color:var(--ink3); margin:30px 0 12px; }

/* 카드 */
.card{ background:var(--paper); border:1px solid var(--line); border-radius:18px; padding:22px 24px; margin-bottom:14px; }
.card .eyebrow{ font-size:12px; font-weight:700; letter-spacing:.02em; color:var(--ink3); margin-bottom:14px; }

/* 분석 완료 카드 */
.done-row{ display:flex; align-items:baseline; flex-wrap:wrap; gap:4px 10px; }
.done-t{ font-size:1.08rem; font-weight:800; color:var(--ink); letter-spacing:-.02em; }
.done-s{ font-size:.86rem; color:var(--ink3); }

/* 핵심 판단(hero) */
.hero .hero-line{ font-size:1.32rem; font-weight:800; color:var(--ink); letter-spacing:-.03em; line-height:1.42; margin-bottom:12px; }
.hero .hero-q{ font-size:.92rem; color:var(--ink2); padding-left:13px; border-left:2px solid var(--blue); margin-bottom:16px; }
.pill{ display:inline-block; font-size:.8rem; font-weight:700; color:var(--blue); background:var(--blue-soft);
  border:1px solid #DCEAFE; border-radius:999px; padding:5px 13px; }

/* 정의형 행 */
.kv{ display:flex; flex-direction:column; }
.kv-row{ display:flex; gap:16px; padding:12px 0; border-top:1px solid var(--line); }
.kv-row:first-child{ border-top:none; }
.kv-l{ flex:0 0 88px; font-size:.85rem; font-weight:700; color:var(--ink3); padding-top:1px; }
.kv-v{ flex:1; font-size:.92rem; color:var(--ink); }

/* 요인/리스크 */
.lede{ font-size:.82rem; color:var(--ink3); margin:-4px 0 16px; }
.item{ padding:16px 0; border-top:1px solid var(--line); }
.item:first-of-type{ border-top:none; padding-top:2px; }
.item-head{ display:flex; align-items:center; gap:9px; margin-bottom:11px; }
.item-title{ font-size:1.02rem; font-weight:800; color:var(--ink); letter-spacing:-.02em; }
.tag{ font-size:.7rem; font-weight:800; letter-spacing:.02em; padding:3px 9px; border-radius:6px; white-space:nowrap; }
.tag.risk{ color:#C2333A; background:#FDF0F1; } .tag.pos{ color:var(--blue-d); background:var(--blue-soft); }
.f{ display:flex; gap:12px; padding:4px 0; }
.f-l{ flex:0 0 92px; font-size:.8rem; font-weight:700; color:var(--ink3); }
.f-v{ flex:1; font-size:.9rem; color:var(--ink2); }

/* 통계/막대 */
.stats{ display:flex; border:1px solid var(--line); border-radius:14px; overflow:hidden; margin:4px 0 18px; }
.stat{ flex:1; padding:14px 8px; text-align:center; border-left:1px solid var(--line); }
.stat:first-child{ border-left:none; }
.stat .num{ font-size:1.25rem; font-weight:800; color:var(--ink); letter-spacing:-.02em; }
.stat .num.up{ color:var(--up); } .stat .num.down{ color:var(--down); }
.stat .cap{ font-size:.72rem; color:var(--ink3); margin-top:3px; }
.bars{ display:flex; gap:3px; align-items:stretch; height:84px; position:relative; margin:6px 0 16px; }
.bars::after{ content:""; position:absolute; left:0; right:0; top:50%; border-top:1px dashed var(--line); }
.bcol{ flex:1; display:flex; flex-direction:column; min-width:0; }
.bhalf{ height:42px; display:flex; justify-content:center; }
.bhalf.top{ align-items:flex-end; } .bhalf.bot{ align-items:flex-start; }
.bar{ width:62%; max-width:13px; border-radius:3px; }
.bar.up{ background:var(--up); } .bar.dn{ background:var(--down); }

.cap{ font-size:.78rem; color:var(--ink3); margin-top:8px; line-height:1.55; }
.body{ font-size:.92rem; color:var(--ink); margin-bottom:6px; }

/* 성향별 가이드 */
.guide-hero{ font-size:1.02rem; font-weight:700; color:var(--ink); line-height:1.6; letter-spacing:-.01em;
  padding:16px 18px; background:var(--blue-soft); border-radius:14px; margin-bottom:16px; }
.guide-grid{ display:grid; grid-template-columns:1fr 1fr 1fr; gap:10px; }
.guide{ border:1px solid var(--line); border-radius:14px; padding:14px; }
.guide .gl{ font-size:.76rem; font-weight:800; color:var(--blue); margin-bottom:7px; }
.guide .gt{ font-size:.83rem; color:var(--ink2); line-height:1.55; }
@media (max-width:640px){ .guide-grid{ grid-template-columns:1fr; } }

/* 공시 링크 */
.disc-base{ display:block; padding:15px 18px; border:1px solid #DCEAFE; background:var(--blue-soft);
  border-radius:14px; margin-bottom:16px; text-decoration:none; }
.disc-base .dl{ font-size:.74rem; font-weight:800; color:var(--blue); letter-spacing:.02em; }
.disc-base .dt{ display:block; font-size:1rem; font-weight:800; color:var(--ink); margin-top:5px; letter-spacing:-.02em; }
.disc-list{ display:flex; flex-direction:column; }
.disc-row{ display:flex; align-items:baseline; gap:14px; padding:11px 0; border-top:1px solid var(--line); }
.disc-row:first-child{ border-top:none; }
.disc-date{ flex:0 0 78px; font-size:.78rem; color:var(--ink3); font-variant-numeric:tabular-nums; }
.disc-title{ font-size:.9rem; font-weight:600; }
.disc-title a{ color:var(--ink) !important; text-decoration:none; }
.disc-title a:hover{ color:var(--blue) !important; text-decoration:underline; }
.disc-base-tag{ font-size:.68rem; font-weight:800; color:var(--blue); margin-left:6px; }

/* 칩/헤더 */
.chips{ display:flex; flex-wrap:wrap; gap:7px; margin:6px 0 4px; }
.chip{ font-size:.8rem; font-weight:700; color:var(--ink2); background:var(--line2); border:1px solid var(--line); border-radius:999px; padding:5px 12px; }
.chip b{ color:var(--ink); }
.rep-co{ font-size:1.5rem; font-weight:800; color:var(--ink); letter-spacing:-.03em; }
.rep-co small{ font-size:.85rem; font-weight:600; color:var(--ink3); margin-left:7px; letter-spacing:0; }
.foot-note{ font-size:.76rem; color:var(--ink3); line-height:1.6; margin-top:8px; }
.warn-line{ font-size:.82rem; color:#9A6A00; background:#FFF8E6; border:1px solid #F6E7B8; border-radius:10px; padding:10px 14px; margin:10px 0; }
a{ color:var(--blue); }

/* 위젯 */
.stButton>button, [data-testid="stFormSubmitButton"]>button{
  background:var(--blue) !important; color:#fff !important; border:none !important; border-radius:13px !important;
  font-weight:700 !important; padding:.74rem 1rem !important; box-shadow:none !important; }
.stButton>button:hover, [data-testid="stFormSubmitButton"]>button:hover{ background:var(--blue-d) !important; }
[data-testid="stVerticalBlockBorderWrapper"]{ border:1px solid var(--line) !important; border-radius:18px !important; padding:18px 20px !important; box-shadow:none !important; }
input, textarea, [data-baseweb="input"], [data-baseweb="base-input"]{ border-radius:11px !important; }
.stTextInput input:focus{ border-color:var(--blue) !important; box-shadow:0 0 0 3px var(--blue-soft) !important; }
hr{ border-color:var(--line) !important; }
[data-testid="stExpander"]{ border:1px solid var(--line) !important; border-radius:13px !important; box-shadow:none !important; }
[data-testid="stExpander"] summary{ font-weight:600 !important; color:var(--ink2) !important; }
[data-testid="stSidebar"]{ background:#FBFBFC; border-right:1px solid var(--line); }
[data-testid="stSidebar"] .stButton>button{ background:#fff !important; color:var(--blue) !important; border:1px solid var(--blue) !important; }
code{ background:var(--line2) !important; color:var(--ink2) !important; border-radius:5px; padding:1px 6px; font-size:.85em; }

/* 페이지 링크(하이퍼링크 버튼) */
[data-testid="stPageLink"] a{ background:var(--blue) !important; border-radius:13px !important;
  padding:.62rem 1.1rem !important; display:inline-flex !important; justify-content:center; }
[data-testid="stPageLink"] a:hover{ background:var(--blue-d) !important; }
[data-testid="stPageLink"] a p{ color:#fff !important; font-weight:700 !important; }
[data-testid="stPageLink"] a svg{ color:#fff !important; }
[data-testid="stPageLink"].ghost a{ background:transparent !important; padding:.3rem 0 !important; }
[data-testid="stPageLink"].ghost a p{ color:var(--blue) !important; }

/* 분석 완료 카드 — 여백 축소 + 텍스트/버튼 상단 정렬 */
[data-testid="stVerticalBlockBorderWrapper"]:has(.done-t){ padding:16px 22px !important; }
[data-testid="stVerticalBlockBorderWrapper"]:has(.done-t) [data-testid="stMarkdownContainer"]{ margin:0 !important; }
[data-testid="stVerticalBlockBorderWrapper"]:has(.done-t) [data-testid="stMarkdownContainer"] p{ margin:0 !important; }
[data-testid="stVerticalBlockBorderWrapper"]:has(.done-t) [data-testid="stPageLink"]{ margin:0 !important; }
[data-testid="stVerticalBlockBorderWrapper"]:has(.done-t) [data-testid="stVerticalBlock"]{ gap:0 !important; }

.side-title{ font-size:.95rem; font-weight:800; color:var(--ink); margin:2px 0 12px; }
.srow{ display:flex; align-items:center; gap:9px; margin-top:14px; }
.dot{ width:8px; height:8px; border-radius:50%; flex:0 0 8px; }
.srow .sn{ font-size:.85rem; font-weight:700; color:var(--ink); }
.sdetail{ font-size:.76rem; color:var(--ink3); margin:3px 0 0 17px; line-height:1.5; }
.side-foot{ font-size:.74rem; color:var(--ink3); margin-top:20px; line-height:1.6; }
</style>
""")

_DOT = {"live": "#21BA72", "fallback": "#F5A623", "error": "#EC4848"}

# ---------------------------------------------------------------------------
# 공통: 사이드바 + 상단 로고/면책 (두 페이지에 표시)
# ---------------------------------------------------------------------------
with st.sidebar:
    H('<div class="side-title">연동 상태</div>')
    probe = st.button("연결 테스트 실행", use_container_width=True,
                      help="DART·네이버는 무료, LLM은 토큰을 소량 사용합니다.")
    rows = []
    for s in run_all(probe=probe):
        rows.append(
            f'<div class="srow"><span class="dot" style="background:{_DOT.get(s.level, "#ccc")}"></span>'
            f'<span class="sn">{esc(s.name)}</span></div><div class="sdetail">{esc(s.detail)}</div>'
        )
    H("".join(rows))
    H('<div class="side-foot">라이브 · 폴백 · 오류 상태를 표시합니다. 키는 <code>.env</code> 입력 후 앱 재시작 시 반영됩니다.</div>')

H(
    '<div class="masthead">'
    '<div class="logo-word"><span class="lg b">살</span><span class="sm b">까</span>'
    '<span class="lg k">말</span><span class="sm k">까</span><span class="q">?</span></div>'
    '<div class="sub">공시 기반 투자 의사결정 참고 리포트 · DART 사업보고서·네이버 트렌드·과거 주가 반응·성향별 판단 기준을 융합한 개인화 참고 정보</div>'
    "</div>"
)
H(
    '<div class="disclaimer-note">본 서비스는 투자 참고용 통계 정보이며 법적 투자자문이 아닙니다. '
    "매수·매도를 권유하지 않으며, 과거 주가 반응은 미래 수익을 보장하지 않습니다. 최종 판단과 책임은 "
    "사용자 본인에게 있습니다. 입력 정보는 세션 내에서만 처리되며 저장되지 않습니다.</div>"
)


# ---------------------------------------------------------------------------
# 리포트 렌더 헬퍼
# ---------------------------------------------------------------------------
def card(eyebrow: str, inner: str) -> None:
    H(f'<div class="card"><div class="eyebrow">{eyebrow}</div>{inner}</div>')


def factor_item(it: dict, kind: str) -> str:
    label = "리스크" if kind == "risk" else "긍정 요인"
    tag_cls = "risk" if kind == "risk" else "pos"
    fields = [("근거", it.get("evidence")), ("왜 중요한가", it.get("why_it_matters"))]
    if kind == "risk":
        fields += [("나에게 주는 의미", it.get("user_impact")), ("모니터링 지표", it.get("monitoring_signal"))]
    else:
        fields += [("투자 판단상 의미", it.get("investment_implication"))]
    body = "".join(
        f'<div class="f"><div class="f-l">{esc(l)}</div><div class="f-v">{esc(v)}</div></div>'
        for l, v in fields if v
    )
    cat = esc(it.get("category") or label)
    return (
        f'<div class="item"><div class="item-head"><span class="tag {tag_cls}">{cat}</span>'
        f'<span class="item-title">{esc(it.get("title"))}</span></div>{body}</div>'
    )


def price_bars(events: list) -> str:
    if not events:
        return ""
    vals = [float(e.get("ret_5d", 0)) for e in events]
    mx = max((abs(v) for v in vals), default=0) or 1.0
    cols = []
    for e in events:
        v = float(e.get("ret_5d", 0))
        h = round(min(abs(v) / mx, 1) * 40)
        up = v >= 0
        tip = f'{esc(e.get("date"))} · {v*100:+.1f}%'
        top = f'<span class="bar up" style="height:{h}px"></span>' if up else ""
        bot = f'<span class="bar dn" style="height:{h}px"></span>' if not up else ""
        cols.append(f'<div class="bcol" title="{tip}"><div class="bhalf top">{top}</div><div class="bhalf bot">{bot}</div></div>')
    return f'<div class="bars">{"".join(cols)}</div>'


def render_report_body(data: dict) -> None:
    res = data["res"]
    company, ticker, market = data["company"], data["ticker"], data["market"]
    weight, risk_profile, horizon = data["weight"], data["risk_profile"], data["horizon"]
    bucket = config.weight_bucket(float(weight))
    risk_level = config.WEIGHT_BUCKET_GUIDE[bucket]["risk_level"]

    H(
        f'<div class="rep-co">{esc(company)}<small>{esc(ticker)} · {esc(market)}</small></div>'
        '<div class="chips">'
        f'<span class="chip"><b>{esc(risk_profile)}</b></span>'
        f'<span class="chip"><b>{esc(horizon)}</b></span>'
        f'<span class="chip">보유 비중 <b>{weight:.0f}%</b></span>'
        f'<span class="chip">{esc(bucket)} · {esc(risk_level)}</span></div>'
    )
    if not res.get("llm_used"):
        H(f'<div class="warn-line">{esc(res.get("llm_note", "규칙기반 분석으로 표시 중입니다."))}</div>')

    thesis = res.get("investment_thesis", {})
    summary = res.get("company_summary", {})
    sources = res.get("disclosure_sources", [])
    recents = res.get("recent_disclosures", [])
    base_rno = {s.get("rcept_no") for s in sources}

    if thesis.get("one_line"):
        inner = f'<div class="hero-line">{esc(thesis.get("one_line"))}</div>'
        if thesis.get("key_question"):
            inner += f'<div class="hero-q">{esc(thesis.get("key_question"))}</div>'
        if thesis.get("overall_stance"):
            inner += f'<span class="pill">{esc(thesis.get("overall_stance"))}</span>'
        H(f'<div class="card hero"><div class="eyebrow">핵심 투자 판단</div>{inner}</div>')

    if sources or recents:
        inner = ""
        for s in sources:
            tag = '<span class="dl">현재 분석 기반 · 최신 정기보고서</span>'
            label = f'<span class="dt">{esc(s.get("label"))}</span>'
            if s.get("url"):
                inner += f'<a class="disc-base" href="{esc(s.get("url"))}" target="_blank">{tag}{label}</a>'
            else:
                inner += f'<div class="disc-base">{tag}{label}</div>'
        if recents:
            rowhtml = ""
            for r in recents:
                title, d, url = esc(r.get("title")), esc(r.get("date")), r.get("url", "")
                base = '<span class="disc-base-tag">분석 기반</span>' if r.get("rcept_no") and r.get("rcept_no") in base_rno else ""
                link = f'<a href="{esc(url)}" target="_blank">{title}</a>' if url else title
                rowhtml += f'<div class="disc-row"><span class="disc-date">{d}</span><span class="disc-title">{link}{base}</span></div>'
            inner += f'<div class="disc-list">{rowhtml}</div><div class="cap">제목을 누르면 DART 공시 원문으로 이동합니다.</div>'
        card("근거 공시", inner)

    rows = [
        ("사업 구조", summary.get("business_structure")),
        ("현재 위치", summary.get("current_position")),
        ("재무 건전성", summary.get("financial_quality")),
        ("성장 동력", summary.get("growth_driver")),
        ("핵심 불확실성", summary.get("main_uncertainty")),
    ]
    kv = "".join(f'<div class="kv-row"><div class="kv-l">{esc(l)}</div><div class="kv-v">{esc(v)}</div></div>' for l, v in rows if v)
    if kv:
        card("기업 핵심 요약", f'<div class="kv">{kv}</div>')

    risks = res.get("risk_factors", [])
    if risks:
        items = "".join(factor_item(r, "risk") for r in risks)
        card("공시 기반 리스크", f'<div class="lede">긍정 요인보다 리스크를 먼저 검토합니다.</div>{items}')

    pos = res.get("positive_factors", [])
    if pos:
        card("공시 기반 긍정 요인", "".join(factor_item(p, "pos") for p in pos))

    tr = res.get("trend_interpretation", {})
    if tr.get("interpretation") or tr.get("trend_signal"):
        inner = ""
        if tr.get("trend_signal"):
            inner += f'<div class="body">{esc(tr.get("trend_signal"))}</div>'
        if tr.get("interpretation"):
            inner += f'<div class="body">{esc(tr.get("interpretation"))}</div>'
        inner += f'<div class="cap">{esc(tr.get("caution") or "트렌드·뉴스는 관심·변동성 신호일 뿐 호재·악재 방향을 의미하지 않습니다.")}</div>'
        card("최근 트렌드 해석", inner)

    pr = res.get("historical_price_reaction", {})
    mean = pr.get("mean_5d_return", 0) or 0
    mean_cls = "up" if mean >= 0 else "down"
    stats = (
        '<div class="stats">'
        f'<div class="stat"><div class="num">{pr.get("n", 0)}</div><div class="cap">표본</div></div>'
        f'<div class="stat"><div class="num {mean_cls}">{mean*100:+.1f}%</div><div class="cap">평균 5거래일</div></div>'
        f'<div class="stat"><div class="num down">{(pr.get("min_5d_return", 0) or 0)*100:+.1f}%</div><div class="cap">최저</div></div>'
        f'<div class="stat"><div class="num up">{(pr.get("max_5d_return", 0) or 0)*100:+.1f}%</div><div class="cap">최고</div></div></div>'
    )
    inner = (f'<div class="body">{esc(pr.get("summary"))}</div>' if pr.get("summary") else "") + stats
    inner += price_bars(pr.get("events", []))
    if pr.get("how_to_use"):
        inner += f'<div class="cap">{esc(pr.get("how_to_use"))}</div>'
    inner += f'<div class="cap">{esc(pr.get("caution") or "과거 통계일 뿐 미래 수익을 보장하지 않습니다.")}</div>'
    card(f"과거 주가 반응 · 유사 공시 이후 {config.PRICE_REACTION_WINDOW}거래일", inner)

    g = res.get("personalized_guidance", {})
    inner = ""
    if g.get("narrative"):
        inner += f'<div class="guide-hero">{esc(g.get("narrative"))}</div>'
    if g.get("recommended_stance"):
        inner += f'<span class="pill">{esc(g.get("recommended_stance"))}</span>'
    if g.get("rationale"):
        inner += f'<div class="cap" style="margin:12px 0 16px">{esc(g.get("rationale"))}</div>'
    ag = g.get("action_guide", {})
    guides = [("현재 보유자", ag.get("current_holding")), ("추가 매수", ag.get("additional_buying")), ("리스크 관리", ag.get("risk_control"))]
    gh = "".join(f'<div class="guide"><div class="gl">{esc(l)}</div><div class="gt">{esc(v or "-")}</div></div>' for l, v in guides)
    inner += f'<div class="guide-grid">{gh}</div><div class="cap">구체적 목표가·수량 없이 범주형 가이드만 제공합니다.</div>'
    card("성향별 투자 방향", inner)

    H(f'<div class="foot-note">{esc(res.get("disclaimer"))}</div>')
    with st.expander("원본 데이터 보기"):
        st.json(res)


# ---------------------------------------------------------------------------
# 페이지 1 — 분석 (입력 + 실행 + 리포트 보기 링크)
# ---------------------------------------------------------------------------
def page_analyze() -> None:
    H('<div class="section-label">분석 정보 입력</div>')
    with st.form("input_form"):
        company = st.text_input("기업명", value="삼성전자", help="예: 삼성전자, SK하이닉스")
        col1, col2 = st.columns(2)
        with col1:
            weight = st.slider("보유 비중 (%)", min_value=0.0, max_value=100.0, value=15.0, step=1.0)
            risk_profile = st.radio("투자 성향", config.RISK_PROFILES, index=1, horizontal=True)
        with col2:
            horizon = st.radio("투자 기간", config.HORIZONS, index=1, horizontal=True)
            focus_raw = st.text_input("관심 포인트", value="HBM, 배당")
        submitted = st.form_submit_button("분석하기", use_container_width=True)

    if submitted:
        if weight > 100:
            H('<div class="warn-line">보유 비중은 100%를 초과할 수 없습니다.</div>')
            return
        if not company.strip():
            H('<div class="warn-line">기업명을 입력해 주세요.</div>')
            return
        info = resolve_corp(company.strip())
        if info is None:
            H(f'<div class="warn-line">\'{esc(company)}\' 종목코드를 찾지 못했습니다. 기업명을 확인해 주세요. (예: 삼성전자)</div>')
            return
        user_input = {
            "company": info.company, "ticker": info.ticker, "market": info.market,
            "weight": float(weight), "held": weight > 0, "risk_profile": risk_profile,
            "horizon": horizon, "focus_points": [s.strip() for s in focus_raw.split(",") if s.strip()],
        }
        with st.spinner("공시·트렌드·과거 주가 반응·판단 기준을 분석하고 있습니다. 처음 보는 기업은 보고서를 받아오느라 조금 더 걸립니다."):
            res = analyze(user_input).model_dump()
        st.session_state["report_data"] = {
            "res": res, "company": info.company, "ticker": info.ticker, "market": info.market,
            "weight": float(weight), "risk_profile": risk_profile, "horizon": horizon,
        }

    # 분석 결과가 있으면 "분석 완료 + 리포트 보기" 안내
    data = st.session_state.get("report_data")
    if data:
        with st.container(border=True):
            c1, c2 = st.columns([0.62, 0.38], vertical_alignment="center")
            with c1:
                H('<div class="done-row"><span class="done-t">분석 완료</span>'
                  f'<span class="done-s">{esc(data["company"])} · 리포트가 준비되었습니다</span></div>')
            with c2:
                st.page_link(REPORT_PAGE, label="리포트 보기  →", use_container_width=True)
    else:
        H('<div class="cap" style="margin-top:18px">정보를 입력하고 분석하기를 누르면 리포트가 생성됩니다.</div>')


# ---------------------------------------------------------------------------
# 페이지 2 — 리포트 (세션 결과 렌더)
# ---------------------------------------------------------------------------
def page_report() -> None:
    data = st.session_state.get("report_data")
    st.page_link(ANALYZE_PAGE, label="←  새 분석 하기")
    if not data:
        H('<div class="cap" style="margin-top:14px">아직 생성된 리포트가 없습니다. 분석 페이지에서 먼저 분석을 실행해 주세요.</div>')
        return
    H('<div class="section-label">분석 리포트</div>')
    render_report_body(data)


ANALYZE_PAGE = st.Page(page_analyze, title="분석", url_path="analyze", default=True)
REPORT_PAGE = st.Page(page_report, title="리포트", url_path="report")
st.navigation([ANALYZE_PAGE, REPORT_PAGE], position="hidden").run()
