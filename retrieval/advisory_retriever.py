"""vectorDB #2 (advisory) 검색기. disclosure와 완전히 분리된 컬렉션을 사용한다."""
from __future__ import annotations

from functools import lru_cache
from typing import List

from utils import ensure_root_on_path

ensure_root_on_path()
import config  # noqa: E402
from vectorstore import LocalVectorStore, SearchHit  # noqa: E402


@lru_cache(maxsize=1)
def _store() -> LocalVectorStore:
    return LocalVectorStore(config.ADVISORY_STORE, config.ADVISORY_COLLECTION).load()


def search(query: str, top_k: int = None) -> List[SearchHit]:
    top_k = top_k or config.ADVISORY_TOP_K
    return _store().query(query, top_k=top_k)


if __name__ == "__main__":
    import sys

    q = sys.argv[1] if len(sys.argv) > 1 else "중립형 30% 이상 악재 행동 제안"
    for h in search(q):
        print(f"[{h.score:.3f}] {h.metadata.get('section')} :: {h.text[:80]}...")
