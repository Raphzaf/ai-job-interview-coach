"""Builds the application's long-lived services once and exposes them to routes.

The embedding model and tokenizer take a few seconds to load, so they are
created once at startup and shared by all requests (and all sessions).
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request

from app.core.config import Settings
from app.core.sessions import SessionStore
from app.document_processing.processor import DocumentProcessor
from app.document_processing.tokenizer import ApproximateTokenCounter, TokenCounter, build_token_counter
from app.embeddings.service import EmbeddingService, build_embedding_service
from app.rag.llm import LLMProvider, build_llm_provider
from app.rag.pipeline import CoachPipeline


@dataclass
class Container:
    settings: Settings
    pipeline: CoachPipeline


def build_container(
    settings: Settings,
    embedder: EmbeddingService | None = None,
    llm: LLMProvider | None | str = "auto",
    token_counter: TokenCounter | None = None,
) -> Container:
    """Wire the services. Tests inject fakes through the optional arguments."""
    embedder = embedder or build_embedding_service(settings.embedding_provider, settings.embedding_model)
    if token_counter is None:
        token_counter = (
            build_token_counter(settings.embedding_provider, settings.embedding_model)
            if settings.embedding_provider == "sentence_transformers"
            else ApproximateTokenCounter()
        )
    provider = build_llm_provider(settings) if llm == "auto" else llm
    pipeline = CoachPipeline(
        settings=settings,
        processor=DocumentProcessor(settings, token_counter),
        embedder=embedder,
        llm=provider,  # type: ignore[arg-type]
        sessions=SessionStore(),
    )
    return Container(settings=settings, pipeline=pipeline)


def get_container(request: Request) -> Container:
    return request.app.state.container


def get_pipeline(request: Request) -> CoachPipeline:
    return request.app.state.container.pipeline
