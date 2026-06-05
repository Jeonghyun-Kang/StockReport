"""임베딩 추상화. OpenAI 호환 → sentence-transformers → TF-IDF 순으로 graceful fallback.

- 특정 모델에 종속되지 않는다(spec: 모델 비종속).
- TF-IDF는 코퍼스 의존적이므로 build 시 fit 한 vectorizer를 store와 함께 영속한다.
"""
from __future__ import annotations

import pickle
from typing import List

import numpy as np

import config


def _l2_normalize(mat: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return mat / norms


class DenseEmbedder:
    """OpenAI 호환 임베딩 또는 sentence-transformers 백엔드."""

    requires_fit = False

    def __init__(self, backend: str, model: str):
        self.backend = backend          # "openai" | "sbert"
        self.model = model
        self._client = None
        self._st = None

    @property
    def name(self) -> str:
        return f"{self.backend}:{self.model}"

    def _ensure(self):
        if self.backend == "openai" and self._client is None:
            from openai import OpenAI

            self._client = OpenAI(
                base_url=config.EMBEDDING_BASE_URL or config.LLM_BASE_URL,
                api_key=config.EMBEDDING_API_KEY or config.LLM_API_KEY,
            )
        elif self.backend == "sbert" and self._st is None:
            from sentence_transformers import SentenceTransformer

            self._st = SentenceTransformer(self.model)

    def encode(self, texts: List[str]) -> np.ndarray:
        self._ensure()
        if self.backend == "openai":
            resp = self._client.embeddings.create(model=self.model, input=list(texts))
            vecs = np.array([d.embedding for d in resp.data], dtype=np.float32)
        else:
            vecs = np.asarray(
                self._st.encode(list(texts), show_progress_bar=False), dtype=np.float32
            )
        return _l2_normalize(vecs)


class TfidfEmbedder:
    """scikit-learn TF-IDF fallback. 문자 n-gram으로 한국어 토큰화 부담을 줄인다."""

    requires_fit = True
    name = "tfidf:char_wb(2,4)"

    def __init__(self):
        self._vectorizer = None

    def fit(self, texts: List[str]) -> None:
        from sklearn.feature_extraction.text import TfidfVectorizer

        self._vectorizer = TfidfVectorizer(
            analyzer="char_wb", ngram_range=(2, 4), min_df=1, max_features=50000
        )
        self._vectorizer.fit(texts)

    def encode(self, texts: List[str]) -> np.ndarray:
        if self._vectorizer is None:
            raise RuntimeError("TfidfEmbedder must be fit() before encode()")
        mat = self._vectorizer.transform(list(texts)).toarray().astype(np.float32)
        return _l2_normalize(mat)

    def dumps(self) -> bytes:
        return pickle.dumps(self._vectorizer)

    def loads(self, blob: bytes) -> None:
        self._vectorizer = pickle.loads(blob)


def get_embedder() -> "DenseEmbedder | TfidfEmbedder":
    """환경에 따라 사용 가능한 최선의 임베더를 선택한다."""
    # 1) OpenAI 호환 임베딩 (명시적으로 키/모델/베이스 지정된 경우)
    if config.EMBEDDING_API_MODEL and (config.EMBEDDING_BASE_URL or config.LLM_BASE_URL):
        try:
            import openai  # noqa: F401

            return DenseEmbedder("openai", config.EMBEDDING_API_MODEL)
        except Exception:
            pass

    # 2) sentence-transformers (한국어 모델)
    try:
        import sentence_transformers  # noqa: F401

        return DenseEmbedder("sbert", config.EMBEDDING_MODEL)
    except Exception:
        pass

    # 3) TF-IDF fallback (항상 동작)
    return TfidfEmbedder()


def rebuild_embedder(name: str) -> "DenseEmbedder | TfidfEmbedder":
    """store에 저장된 backend 이름으로부터 동일한 임베더를 재구성한다(쿼리 시)."""
    if name.startswith("openai:"):
        return DenseEmbedder("openai", name.split(":", 1)[1])
    if name.startswith("sbert:"):
        return DenseEmbedder("sbert", name.split(":", 1)[1])
    return TfidfEmbedder()
