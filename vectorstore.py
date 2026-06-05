"""경량 로컬 벡터스토어 (numpy 코사인 유사도 기반).

- 컬렉션 2개(disclosure/advisory)를 서로 다른 디렉터리에 영속하여 완전히 분리한다.
- 영속 파일: vectors.npy, docs.json, backend.json, (TF-IDF인 경우) tfidf.pkl
- chromadb/faiss 대신 외부 네이티브 의존성 없이 동작하도록 자체 구현(MVP 안정성 우선).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from embeddings import TfidfEmbedder, get_embedder, rebuild_embedder


@dataclass
class SearchHit:
    text: str
    metadata: Dict
    score: float


class LocalVectorStore:
    def __init__(self, path: Path, collection: str):
        self.path = Path(path)
        self.collection = collection
        self._vectors: Optional[np.ndarray] = None
        self._docs: List[Dict] = []
        self._embedder = None

    # ---- 영속 파일 경로 ----
    @property
    def _vec_file(self) -> Path:
        return self.path / "vectors.npy"

    @property
    def _docs_file(self) -> Path:
        return self.path / "docs.json"

    @property
    def _backend_file(self) -> Path:
        return self.path / "backend.json"

    @property
    def _tfidf_file(self) -> Path:
        return self.path / "tfidf.pkl"

    def exists(self) -> bool:
        return self._vec_file.exists() and self._docs_file.exists()

    # ---- 빌드 ----
    def build(self, texts: List[str], metadatas: List[Dict]) -> None:
        assert len(texts) == len(metadatas), "texts/metadatas 길이 불일치"
        self.path.mkdir(parents=True, exist_ok=True)
        embedder = get_embedder()
        if getattr(embedder, "requires_fit", False):
            embedder.fit(texts)
        vectors = embedder.encode(texts)

        np.save(self._vec_file, vectors)
        self._docs = [
            {"text": t, "metadata": m} for t, m in zip(texts, metadatas)
        ]
        self._docs_file.write_text(
            json.dumps(self._docs, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self._backend_file.write_text(
            json.dumps(
                {"collection": self.collection, "backend": embedder.name, "count": len(texts)},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        if isinstance(embedder, TfidfEmbedder):
            self._tfidf_file.write_bytes(embedder.dumps())

        self._vectors = vectors
        self._embedder = embedder

    # ---- 로드 ----
    def load(self) -> "LocalVectorStore":
        if not self.exists():
            raise FileNotFoundError(
                f"벡터스토어가 없습니다: {self.path} — 먼저 인덱스를 빌드하세요."
            )
        self._vectors = np.load(self._vec_file)
        self._docs = json.loads(self._docs_file.read_text(encoding="utf-8"))
        backend = json.loads(self._backend_file.read_text(encoding="utf-8"))["backend"]
        self._embedder = rebuild_embedder(backend)
        if isinstance(self._embedder, TfidfEmbedder):
            self._embedder.loads(self._tfidf_file.read_bytes())
        return self

    # ---- 추가(append) — 온디맨드 인덱싱 ----
    def add_documents(self, texts: List[str], metadatas: List[Dict]) -> None:
        """기존 스토어에 문서를 추가한다(없으면 새로 빌드).

        - dense(sbert/openai) 백엔드: 신규 문서만 인코딩해 이어붙임.
        - TF-IDF 백엔드: 어휘 갱신 위해 전체 코퍼스로 refit 후 재인코딩.
        """
        if not texts:
            return
        if not self.exists():
            return self.build(texts, metadatas)

        from embeddings import TfidfEmbedder, rebuild_embedder

        self.load()
        backend = json.loads(self._backend_file.read_text(encoding="utf-8"))["backend"]
        embedder = rebuild_embedder(backend)

        new_docs = [{"text": t, "metadata": m} for t, m in zip(texts, metadatas)]
        all_docs = self._docs + new_docs

        if isinstance(embedder, TfidfEmbedder):
            all_texts = [d["text"] for d in all_docs]
            embedder.fit(all_texts)
            vectors = embedder.encode(all_texts)
            self._tfidf_file.write_bytes(embedder.dumps())
        else:
            new_vecs = embedder.encode(texts)
            vectors = np.vstack([self._vectors, new_vecs])

        np.save(self._vec_file, vectors)
        self._docs = all_docs
        self._docs_file.write_text(
            json.dumps(all_docs, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self._backend_file.write_text(
            json.dumps(
                {"collection": self.collection, "backend": embedder.name, "count": len(all_docs)},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self._vectors = vectors
        self._embedder = embedder

    # ---- 검색 ----
    def query(self, text: str, top_k: int = 5, where: Optional[Dict] = None) -> List[SearchHit]:
        if self._vectors is None:
            self.load()
        q = self._embedder.encode([text])[0]
        sims = self._vectors @ q  # 벡터는 L2 정규화되어 있으므로 내적 = 코사인 유사도

        order = np.argsort(-sims)
        hits: List[SearchHit] = []
        for idx in order:
            doc = self._docs[int(idx)]
            if where and not all(doc["metadata"].get(k) == v for k, v in where.items()):
                continue
            hits.append(
                SearchHit(text=doc["text"], metadata=doc["metadata"], score=float(sims[idx]))
            )
            if len(hits) >= top_k:
                break
        return hits
