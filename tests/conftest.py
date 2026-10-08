"""Shared fixtures.

Tests never download models or call a paid API: they use the deterministic
HashingEmbedder, the approximate token counter and a scripted FakeLLM.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import build_container
from app.core.config import Settings
from app.document_processing.processor import DocumentProcessor
from app.document_processing.tokenizer import ApproximateTokenCounter
from app.embeddings.service import CachedEmbedder, HashingEmbedder
from app.main import create_app
from app.retrieval.retriever import Retriever

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "data" / "examples"
EVAL_DATA = ROOT / "evaluation" / "data"


class FakeLLM:
    """Returns scripted responses in order; records the prompts it received."""

    name = "fake-llm"

    def __init__(self, responses: list[str | Exception]):
        self.responses = list(responses)
        self.calls: list[list[dict]] = []

    def complete(self, messages, json_mode=True):
        self.calls.append(messages)
        if not self.responses:
            raise AssertionError("FakeLLM ran out of scripted responses")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


VALID_INSIGHTS = json.dumps({
    "summary": "Strong fit for the role based on RAG and NLP experience [S1].",
    "strengths": ["Built a RAG assistant [S1]"],
    "gaps": ["No AWS experience in the CV [S2]"],
    "recommendations": ["General advice: prepare an AWS deployment example."],
})
VALID_QUESTION = json.dumps({
    "question": "How did you choose the FAISS index for your RAG assistant at Brightleaf?",
    "category": "technical",
    "difficulty": "medium",
    "focus": "Vector Databases",
    "rationale": "The job requires vector search [S1] and the CV mentions FAISS [S2].",
    "expected_points": ["Index type choice", "Scale and latency trade-offs"],
})
VALID_EVALUATION = json.dumps({
    "criteria": {"relevance": 8, "specificity": 6, "structure": 7, "job_alignment": 7},
    "strengths": ["Concrete example"],
    "weaknesses": ["No metrics"],
    "missing_points": ["Latency numbers"],
    "improvement_suggestions": ["Quantify the impact"],
    "improved_answer": "At Brightleaf I chose a flat index because [corpus size] was small...",
    "grounding_note": "FAISS usage comes from the CV [S1].",
})


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, llm_provider="offline", embedding_provider="hashing", log_level="WARNING")


@pytest.fixture
def counter() -> ApproximateTokenCounter:
    return ApproximateTokenCounter()


@pytest.fixture
def embedder() -> CachedEmbedder:
    return CachedEmbedder(HashingEmbedder(dimension=256))


@pytest.fixture
def processor(settings, counter) -> DocumentProcessor:
    return DocumentProcessor(settings, counter)


@pytest.fixture
def sample_cv_text() -> str:
    return (EXAMPLES / "sample_cv.txt").read_text(encoding="utf-8")


@pytest.fixture
def sample_job_text() -> str:
    return (EXAMPLES / "sample_job_description.txt").read_text(encoding="utf-8")


@pytest.fixture
def sample_docs(processor, sample_cv_text, sample_job_text):
    cv = processor.prepare(sample_cv_text, "cv", "sample_cv.txt")
    job = processor.prepare(sample_job_text, "job", "sample_job.txt")
    return cv, job


@pytest.fixture
def retriever(processor, embedder, sample_docs) -> Retriever:
    cv, job = sample_docs
    return Retriever.from_chunks(embedder, processor.chunk(cv) + processor.chunk(job))


def make_client(settings: Settings, llm=None, raise_server_exceptions: bool = True) -> TestClient:
    container = build_container(
        settings, embedder=CachedEmbedder(HashingEmbedder(256)), llm=llm, token_counter=ApproximateTokenCounter()
    )
    return TestClient(create_app(settings, container=container), raise_server_exceptions=raise_server_exceptions)


@pytest.fixture
def client(settings) -> TestClient:
    with make_client(settings) as c:
        yield c
