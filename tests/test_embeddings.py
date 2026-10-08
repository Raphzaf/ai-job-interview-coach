"""Embedding service behaviour (with the deterministic hashing embedder)."""

import numpy as np

from app.embeddings.service import CachedEmbedder, HashingEmbedder


def test_vectors_are_normalised_and_deterministic():
    e = HashingEmbedder(128)
    a = e.embed(["Python developer", "Python developer"])
    assert a.shape == (2, 128) and a.dtype == np.float32
    assert np.allclose(np.linalg.norm(a, axis=1), 1.0)
    assert np.allclose(a[0], a[1])


def test_similar_texts_score_higher():
    e = HashingEmbedder(256)
    q, near, far = e.embed(["python fastapi docker", "built fastapi services in python", "baking bread recipes"])
    assert q @ near > q @ far


def test_empty_text_gives_zero_vector():
    assert not HashingEmbedder(32).embed([""]).any()


def test_cache_avoids_recomputation():
    class Counting(HashingEmbedder):
        calls = 0

        def embed(self, texts):
            Counting.calls += len(texts)
            return super().embed(texts)

    cached = CachedEmbedder(Counting(64))
    first = cached.embed(["a b", "c d"])
    second = cached.embed(["c d", "a b", "e f"])
    assert Counting.calls == 3  # "e f" is the only new text
    assert np.allclose(first[0], second[1])
    assert cached.hits == 2


def test_cache_eviction_keeps_results_correct():
    cached = CachedEmbedder(HashingEmbedder(64), max_entries=1)
    out = cached.embed(["one", "two", "three"])
    assert np.allclose(out, HashingEmbedder(64).embed(["one", "two", "three"]))
