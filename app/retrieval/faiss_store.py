"""FAISS vector store with aligned chunk metadata.

FAISS only stores vectors and returns integer row ids. We keep a Python list
`self._chunks` where position i holds the chunk whose vector is row i of the
index. Because vectors are only ever appended (together with their chunk),
the id -> chunk mapping can never drift, and every search result can be traced
back to its document, section and text.

Index type: `IndexFlatIP` = exact (brute-force) inner-product search. With
normalised vectors inner product == cosine similarity. A CV + job description
produce tens of chunks, so exact search takes microseconds; approximate indexes
(IVF, HNSW) only pay off at hundreds of thousands of vectors and would add
training steps and recall loss for no benefit here.
"""

from __future__ import annotations

import faiss
import numpy as np

from app.core.errors import RetrievalError
from app.models.domain import Chunk, DocType, RetrievedChunk


class FaissVectorStore:
    def __init__(self, dimension: int):
        self.dimension = dimension
        self._index = faiss.IndexFlatIP(dimension)
        self._chunks: list[Chunk] = []

    def __len__(self) -> int:
        return self._index.ntotal

    @property
    def chunks(self) -> list[Chunk]:
        return list(self._chunks)

    def add(self, chunks: list[Chunk], vectors: np.ndarray) -> None:
        if len(chunks) != len(vectors):
            raise RetrievalError(f"Got {len(chunks)} chunks but {len(vectors)} vectors.")
        if len(chunks) == 0:
            return
        vectors = np.ascontiguousarray(vectors, dtype=np.float32)
        if vectors.ndim != 2 or vectors.shape[1] != self.dimension:
            raise RetrievalError(f"Expected vectors of dimension {self.dimension}, got shape {vectors.shape}.")
        self._index.add(vectors)
        self._chunks.extend(chunks)

    def search(self, query_vector: np.ndarray, k: int, doc_type: DocType | None = None) -> list[RetrievedChunk]:
        """Return the k most similar chunks, optionally restricted to one document type."""
        if len(self) == 0:
            return []
        query = np.ascontiguousarray(query_vector, dtype=np.float32).reshape(1, -1)
        if query.shape[1] != self.dimension:
            raise RetrievalError(f"Query dimension {query.shape[1]} != index dimension {self.dimension}.")
        # Metadata filtering: FAISS flat indexes have no native filter, so when a
        # doc_type is requested we score every vector and filter afterwards.
        # That is exact and cheap at this scale (tens of vectors).
        n = len(self) if doc_type else min(k, len(self))
        scores, ids = self._index.search(query, n)
        results: list[RetrievedChunk] = []
        for score, idx in zip(scores[0], ids[0]):
            if idx < 0:
                continue
            chunk = self._chunks[idx]
            if doc_type and chunk.doc_type != doc_type:
                continue
            results.append(RetrievedChunk(chunk=chunk, score=float(score)))
            if len(results) == k:
                break
        return results

    def vectors_for(self, doc_type: DocType) -> np.ndarray:
        """Return stored vectors of one document type (used for document-level similarity)."""
        ids = [i for i, c in enumerate(self._chunks) if c.doc_type == doc_type]
        if not ids:
            return np.zeros((0, self.dimension), dtype=np.float32)
        return np.vstack([self._index.reconstruct(i) for i in ids])
