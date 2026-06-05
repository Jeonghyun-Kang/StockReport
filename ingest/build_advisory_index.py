"""vectorDB #2 (advisory) 빌드: 투자제안 지식문서 → H2 섹션 청킹 → 임베딩 → store/advisory.

vectorDB #1(disclosure)과 완전히 분리된 컬렉션/디렉터리로 빌드한다.
"""
from __future__ import annotations

from utils import ensure_root_on_path, chunk_by_h2

ensure_root_on_path()
import config  # noqa: E402
from vectorstore import LocalVectorStore  # noqa: E402


def build() -> int:
    config.ensure_dirs()
    if not config.KNOWLEDGE_DOC.exists():
        raise SystemExit(f"지식문서가 없습니다: {config.KNOWLEDGE_DOC}")

    md = config.KNOWLEDGE_DOC.read_text(encoding="utf-8")
    sections = chunk_by_h2(md)

    texts = [s["text"] for s in sections]
    metas = [
        {
            "source": "투자제안_지식문서",
            "type": "advisory",
            "section": s["section"],
        }
        for s in sections
    ]

    store = LocalVectorStore(config.ADVISORY_STORE, config.ADVISORY_COLLECTION)
    store.build(texts, metas)
    print(f"[done] advisory 인덱스 빌드 완료: {len(texts)} sections → {config.ADVISORY_STORE}")
    for s in sections:
        print(f"   - {s['section']}")
    return len(texts)


if __name__ == "__main__":
    build()
