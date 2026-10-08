"""FAISS store and semantic retriever."""

import numpy as np
import pytest

from app.core.errors import RetrievalError
from app.models.domain import Chunk
from app.retrieval.faiss_store import FaissVectorStore


def _chunk(i: int, doc_type: str = "cv", text: str = "") -> Chunk:
    return Chunk(chunk_id=f"{doc_type}-{i}", doc_type=doc_type, doc_name="d", section="S", text=text or f"t{i}",
                 position=i, token_count=1)


def test_search_returns_chunk_metadata_in_similarity_order():
    store = FaissVectorStore(3)
    vectors = np.eye(3, dtype=np.float32)
    store.add([_chunk(0), _chunk(1), _chunk(2, "job")], vectors)
    results = store.search(np.array([0.9, 0.1, 0.0]), k=2)
    assert [r.chunk.chunk_id for r in results] == ["cv-0", "cv-1"]
    assert results[0].score > results[1].score


def test_search_filters_by_document_type():
    store = FaissVectorStore(3)
    store.add([_chunk(0), _chunk(1, "job")], np.eye(3, dtype=np.float32)[:2])
    results = store.search(np.array([1.0, 0, 0]), k=5, doc_type="job")
    assert [r.chunk.doc_type for r in results] == ["job"]


def test_empty_store_and_errors():
    store = FaissVectorStore(3)
    assert store.search(np.ones(3), k=3) == []
    with pytest.raises(RetrievalError):
        store.add([_chunk(0)], np.ones((2, 3), dtype=np.float32))
    with pytest.raises(RetrievalError):
        store.add([_chunk(0)], np.ones((1, 4), dtype=np.float32))
    store.add([_chunk(0)], np.ones((1, 3), dtype=np.float32))
    with pytest.raises(RetrievalError):
        store.search(np.ones(4), k=1)


def test_vectors_for_reconstructs_stored_vectors():
    store = FaissVectorStore(2)
    store.add([_chunk(0), _chunk(1, "job")], np.array([[1, 0], [0, 1]], dtype=np.float32))
    assert np.allclose(store.vectors_for("job"), [[0, 1]])


def test_retriever_finds_relevant_cv_chunk(retriever):
    results = retriever.retrieve("FAISS embeddings retrieval-augmented generation assistant", k=3, doc_type="cv")
    assert results and all(r.chunk.doc_type == "cv" for r in results)
    assert "FAISS" in results[0].chunk.text


def test_retrieve_balanced_returns_both_documents(retriever):
    results = retriever.retrieve_balanced("Python Docker FastAPI", k_per_doc=2)
    assert {r.chunk.doc_type for r in results} == {"cv", "job"}
    assert [r.score for r in results] == sorted((r.score for r in results), reverse=True)


def test_min_score_filters_irrelevant_chunks(retriever):
    assert retriever.retrieve("zzzz qqqq", k=5, min_score=0.2) == []
