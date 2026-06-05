"""vectorDB #1 (disclosure) 검색기."""
from __future__ import annotations

from functools import lru_cache
from typing import List, Optional

from utils import ensure_root_on_path

ensure_root_on_path()
import config  # noqa: E402
from vectorstore import LocalVectorStore, SearchHit  # noqa: E402


@lru_cache(maxsize=1)
def _store() -> LocalVectorStore:
    return LocalVectorStore(config.DISCLOSURE_STORE, config.DISCLOSURE_COLLECTION).load()


def search(query: str, top_k: int = None, ticker: Optional[str] = None) -> List[SearchHit]:
    top_k = top_k or config.DISCLOSURE_TOP_K
    where = {"ticker": ticker} if ticker else None
    return _store().query(query, top_k=top_k, where=where)


if __name__ == "__main__":
    import sys

    q = sys.argv[1] if len(sys.argv) > 1 else "삼성전자 HBM 반도체 실적"
    for h in search(q):
        print(f"[{h.score:.3f}] {h.metadata.get('source')} :: {h.text[:80]}...")
