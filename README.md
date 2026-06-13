# StockReport

DART 사업보고서, 뉴스/트렌드, 과거 주가 반응, 투자 성향별 가이드 지식을 활용해 투자 참고 리포트를 생성하는 Streamlit 기반 AI 서비스입니다.

> 본 프로젝트는 투자 참고용 정보 제공 서비스이며, 매수/매도 추천이나 법적 투자자문을 제공하지 않습니다.

## 주요 기능

- 기업명 기반 DART 사업보고서 수집 및 분석
- 공시 기반 RAG 검색
- 네이버 뉴스/트렌드 참고 정보 제공
- yfinance 기반 과거 주가 반응 참고
- 사용자 투자 성향, 보유 비중, 투자 기간 기반 투자 참고 리포트 생성
- Streamlit UI 제공

## 설치

```bash
python3 -m venv .venv
source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt
```

## 데모 영상

<video src="https://github.com/Jeonghyun-Kang/StockReport/raw/main/ai_finance_demo.mp4" controls width="100%"></video>

> 영상이 보이지 않으면 [여기를 눌러 다운로드/재생](https://github.com/Jeonghyun-Kang/StockReport/raw/main/ai_finance_demo.mp4)하세요.

# 공시 기반 투자 의사결정 참고 AI

DART 사업보고서 기반 RAG, 네이버 트렌드/뉴스, 과거 주가 반응, 투자 성향별 가이드 지식을 결합해  

사용자 맞춤형 투자 참고 리포트를 생성하는 Streamlit 기반 AI 서비스입니다.

> 본 프로젝트는 투자 참고용 정보 제공 서비스이며, 매수/매도 추천이나 법적 투자자문을 제공하지 않습니다.
---

## 1. 핵심 기능

- 기업명 기반 DART 사업보고서 수집 및 분석

- 공시 기반 핵심 요약 생성

- 공시 기반 리스크 요인 분석

- 공시 기반 긍정 요인 분석

- 네이버 트렌드/뉴스 기반 관심도 참고 정보 제공

- yfinance 기반 과거 주가 반응 참고

- 사용자 투자 성향, 보유 비중, 투자 기간에 따른 범주형 투자 참고 가이드 제공

- Streamlit UI 제공

- API 키가 없어도 일부 기능은 fallback 방식으로 데모 실행 가능

---
## 2. 전체 아키텍처

```text

사용자 입력

기업명 / 보유 비중 / 투자 성향 / 투자 기간 / 관심 포인트

        ↓

공시 RAG

DART 사업보고서 기반 vector store

        ↓

트렌드 / 뉴스

Naver API 기반 실시간 정보

        ↓

과거 주가 반응

yfinance 기반 단기 수익률 참고

        ↓

투자방향 RAG

성향별 투자 판단 가이드 문서 기반 vector store

        ↓

LLM 분석

공시 근거 + 사용자 조건 + 투자 가드레일 반영

        ↓

Streamlit 리포트 출력
```
---
## 3. .env파일 설정
```bash
DART_API_KEY=

NAVER_CLIENT_ID=
NAVER_CLIENT_SECRET=

LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=
LLM_MODEL=gpt-4o-mini

EMBEDDING_MODEL=jhgan/ko-sroberta-multitask
```

