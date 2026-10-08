"""Embedding service.

An embedding maps a piece of text to a dense vector such that texts with
similar *meaning* end up close to each other, even when they share no words
("built REST services in Flask" ≈ "backend API development in Python").
This is what lets retrieval and matching go beyond keyword search.

The rest of the application only depends on the `EmbeddingService` protocol,
so the model can be swapped (another sentence-transformers model, an API-based
embedding model...) by adding one class and one line in `build_embedding_service`.

All vectors are L2-normalised: the dot product of two unit vectors IS their
cosine similarity, which is what the FAISS inner-product index computes.
"""

from __future__ import annotations

import hashlib
import re
from collections import OrderedDict
from typing import Protocol

import numpy as np

from app.core.errors import EmbeddingError
from app.core.logging import get_logger

logger = get_logger(__name__)


class EmbeddingService(Protocol):
    model_name: str
    dimension: int

    def embed(self, texts: list[str]) -> np.ndarray:
        """Return a float32 array of shape (len(texts), dimension), L2-normalised."""
        ...


class SentenceTransformerEmbedder:
    """Local transformer embedding model (default: all-MiniLM-L6-v2, 384 dims).

    Chosen because it is small (~90 MB), runs on CPU in milliseconds per chunk,
    is free, reproducible (no API drift) and keeps CV data on the machine.
    """

    def __init__(self, model_name: str):
        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(model_name, device="cpu")
        except Exception as exc:
            raise EmbeddingError(f"Could not load embedding model '{model_name}': {exc}") from exc
        self.model_name = model_name
        get_dim = getattr(self._model, "get_embedding_dimension", None) or self._model.get_sentence_embedding_dimension
        self.dimension = int(get_dim())

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dimension), dtype=np.float32)
        try:
            vectors = self._model.encode(
                texts, batch_size=32, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False
            )
        except Exception as exc:
            raise EmbeddingError(f"Embedding failed: {exc}") from exc
        return np.asarray(vectors, dtype=np.float32)


class HashingEmbedder:
    """Deterministic bag-of-words vectors via the hashing trick.

    NOT a semantic model: two texts are only similar if they share words.
    It exists so the test-suite runs instantly, offline and deterministically,
    without downloading a transformer. Never the default for real use.
    """

    _TOKEN_RE = re.compile(r"[a-z0-9+#.]+")

    def __init__(self, dimension: int = 384):
        self.model_name = f"hashing-{dimension}"
        self.dimension = dimension

    def embed(self, texts: list[str]) -> np.ndarray:
        matrix = np.zeros((len(texts), self.dimension), dtype=np.float32)
        for row, text in enumerate(texts):
            for token in self._TOKEN_RE.findall(text.lower()):
                token = token.strip(".")
                if not token:
                    continue
                digest = int(hashlib.md5(token.encode()).hexdigest(), 16)
                matrix[row, digest % self.dimension] += 1.0
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        return matrix / np.where(norms == 0, 1, norms)


class CachedEmbedder:
    """LRU cache in front of any embedder.

    During an interview the same CV/job chunks and similar queries are embedded
    repeatedly; caching by text avoids recomputing identical vectors.
    """

    def __init__(self, inner: EmbeddingService, max_entries: int = 5_000):
        self.inner = inner
        self.model_name = inner.model_name
        self.dimension = inner.dimension
        self._cache: OrderedDict[str, np.ndarray] = OrderedDict()
        self._max_entries = max_entries
        self.hits = 0
        self.misses = 0

    def embed(self, texts: list[str]) -> np.ndarray:
        missing = list(dict.fromkeys(t for t in texts if t not in self._cache))
        if missing:
            vectors = self.inner.embed(missing)
            for text, vector in zip(missing, vectors):
                self._cache[text] = vector
                if len(self._cache) > self._max_entries:
                    self._cache.popitem(last=False)
        self.misses += len(missing)
        self.hits += len(texts) - len(missing)
        result = np.zeros((len(texts), self.dimension), dtype=np.float32)
        for i, text in enumerate(texts):
            vector = self._cache.get(text)
            if vector is None:  # evicted within this very call (only with tiny caches)
                vector = self.inner.embed([text])[0]
            else:
                self._cache.move_to_end(text)
            result[i] = vector
        return result


def build_embedding_service(provider: str, model_name: str) -> EmbeddingService:
    if provider == "sentence_transformers":
        logger.info("Loading embedding model %s", model_name)
        inner: EmbeddingService = SentenceTransformerEmbedder(model_name)
    elif provider == "hashing":
        logger.warning("Using the hashing embedder: retrieval is keyword-based, not semantic.")
        inner = HashingEmbedder()
    else:
        raise ValueError(f"Unknown embedding provider: {provider}")
    return CachedEmbedder(inner)
