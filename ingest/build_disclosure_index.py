"""vectorDB #1 (disclosure) 빌드: DART 사업보고서 평문 → 청킹 → 임베딩 → store/disclosure."""
from __future__ import annotations

from typing import List

from utils import ensure_root_on_path, chunk_text

ensure_root_on_path()
import config  # noqa: E402
from vectorstore import LocalVectorStore  # noqa: E402
from ingest.dart_fetch import fetch_latest_report  # noqa: E402


# MVP 시연 대상 핵심 기업
DEFAULT_COMPANIES = ["삼성전자", "SK하이닉스"]


def build(companies: List[str] = None) -> int:
    companies = companies or DEFAULT_COMPANIES
    config.ensure_dirs()

    texts: List[str] = []
    metas: List[dict] = []
    for company in companies:
        rep = fetch_latest_report(company)
        if not rep:
            print(f"[skip] {company}: 보고서 수집 실패")
            continue
        chunks = chunk_text(rep["text"], config.CHUNK_SIZE, config.CHUNK_OVERLAP)
        for i, ch in enumerate(chunks):
            texts.append(ch)
            metas.append(
                {
                    "source": f"{rep['ticker']}_사업보고서",
                    "type": "disclosure",
                    "company": company,
                    "ticker": rep["ticker"],
                    "rcept_no": rep["rcept_no"],
                    "chunk": i,
                }
            )
        print(f"[ok] {company}: {len(chunks)} chunks (rcept_no={rep['rcept_no']})")

    if not texts:
        raise SystemExit("인덱싱할 공시 텍스트가 없습니다.")

    store = LocalVectorStore(config.DISCLOSURE_STORE, config.DISCLOSURE_COLLECTION)
    store.build(texts, metas)
    print(f"[done] disclosure 인덱스 빌드 완료: {len(texts)} chunks → {config.DISCLOSURE_STORE}")
    return len(texts)


def ensure_indexed(company: str, ticker: str = None) -> bool:
    """해당 기업이 공시 인덱스에 없으면 사업보고서를 받아 추가한다. 추가했으면 True."""
    config.ensure_dirs()
    store = LocalVectorStore(config.DISCLOSURE_STORE, config.DISCLOSURE_COLLECTION)
    if store.exists():
        store.load()
        if ticker and any(d["metadata"].get("ticker") == ticker for d in store._docs):
            return False  # 이미 인덱싱됨

    rep = fetch_latest_report(company)
    if not rep:
        return False
    chunks = chunk_text(rep["text"], config.CHUNK_SIZE, config.CHUNK_OVERLAP)
    metas = [
        {
            "source": f"{rep['ticker']}_사업보고서",
            "type": "disclosure",
            "company": company,
            "ticker": rep["ticker"],
            "rcept_no": rep["rcept_no"],
            "chunk": i,
        }
        for i in range(len(chunks))
    ]
    store.add_documents(chunks, metas)
    print(f"[ensure_indexed] {company}({rep['ticker']}) +{len(chunks)} chunks")
    return True


if __name__ == "__main__":
    import sys

    build(sys.argv[1:] or None)
