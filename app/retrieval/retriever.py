"""Semantic retriever: query text -> query embedding -> FAISS top-k -> chunks."""

from __future__ import annotations

from app.core.logging import get_logger
from app.embeddings.service import EmbeddingService
from app.models.domain import Chunk, DocType, RetrievedChunk
from app.retrieval.faiss_store import FaissVectorStore

logger = get_logger(__name__)


class Retriever:
    def __init__(self, embedder: EmbeddingService, store: FaissVectorStore, default_k: int = 4):
        self.embedder = embedder
        self.store = store
        self.default_k = default_k

    @classmethod
    def from_chunks(cls, embedder: EmbeddingService, chunks: list[Chunk], default_k: int = 4) -> "Retriever":
        """Embed chunks and build the FAISS index once; it is then reused for the whole session."""
        store = FaissVectorStore(embedder.dimension)
        vectors = embedder.embed([c.embedding_text for c in chunks])
        store.add(chunks, vectors)
        logger.info("Built FAISS index: %d vectors, dim=%d, model=%s", len(store), embedder.dimension, embedder.model_name)
        return cls(embedder, store, default_k)

    def retrieve(
        self, query: str, k: int | None = None, doc_type: DocType | None = None, min_score: float = 0.0
    ) -> list[RetrievedChunk]:
        # The query is embedded with the SAME model as the chunks; vectors from
        # different models live in different spaces and cannot be compared.
        query_vector = self.embedder.embed([query])[0]
        results = self.store.search(query_vector, k or self.default_k, doc_type=doc_type)
        # A low-similarity "nearest" chunk is still returned by FAISS; dropping it
        # avoids feeding the LLM irrelevant context it might over-interpret.
        return [r for r in results if r.score >= min_score]

    def retrieve_balanced(self, query: str, k_per_doc: int = 3, min_score: float = 0.0) -> list[RetrievedChunk]:
        """Retrieve from the CV and the job description separately.

        A single top-k over both documents can be dominated by one of them;
        interview questions and feedback need evidence from both sides.
        """
        results = self.retrieve(query, k_per_doc, "job", min_score) + self.retrieve(query, k_per_doc, "cv", min_score)
        return sorted(results, key=lambda r: r.score, reverse=True)
