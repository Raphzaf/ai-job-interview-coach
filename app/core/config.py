"""Application configuration.

All tunable values (LLM provider, embedding model, chunk sizes, score weights...)
are read from environment variables or a local `.env` file. Nothing provider-
specific or secret is hard-coded in the source, which lets the same code run
against OpenAI, Gemini, a local Ollama model or the fully offline mode.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- LLM -----------------------------------------------------------------
    llm_provider: Literal["openai_compatible", "offline"] = "openai_compatible"
    llm_model: str = "gpt-4o-mini"
    # SecretStr keeps the key out of repr()/logs by accident.
    llm_api_key: SecretStr = SecretStr("")
    llm_base_url: str = ""
    llm_temperature: float = Field(0.3, ge=0.0, le=2.0)
    llm_timeout_seconds: float = Field(60.0, gt=0)
    llm_fallback_to_offline: bool = True

    # --- Embeddings ----------------------------------------------------------
    embedding_provider: Literal["sentence_transformers", "hashing"] = "sentence_transformers"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    # --- Chunking ------------------------------------------------------------
    # all-MiniLM-L6-v2 truncates anything beyond 256 word-piece tokens, so chunks
    # are kept comfortably below that limit (special tokens + safety margin).
    chunk_max_tokens: int = Field(200, ge=32, le=512)
    chunk_overlap_tokens: int = Field(30, ge=0)

    # --- Retrieval -----------------------------------------------------------
    retrieval_top_k: int = Field(4, ge=1, le=20)

    # --- Matching weights (see app/matching/matcher.py for the rationale) ----
    match_weight_skill_overlap: float = Field(0.40, ge=0)
    match_weight_requirement_coverage: float = Field(0.35, ge=0)
    match_weight_semantic_similarity: float = Field(0.15, ge=0)
    match_weight_experience: float = Field(0.10, ge=0)

    # --- Misc ----------------------------------------------------------------
    log_level: str = "INFO"
    max_upload_mb: float = Field(5.0, gt=0)
    # Hard cap on extracted characters: a CV or job ad is a few pages; anything
    # far larger is almost certainly the wrong file and would slow embedding.
    max_document_chars: int = 60_000
    # Too little text means extraction failed (e.g. scanned PDF) or wrong input.
    min_document_chars: int = 80

    @model_validator(mode="after")
    def _check_overlap(self) -> "Settings":
        if self.chunk_overlap_tokens >= self.chunk_max_tokens:
            raise ValueError("CHUNK_OVERLAP_TOKENS must be smaller than CHUNK_MAX_TOKENS")
        return self

    @property
    def match_weights(self) -> dict[str, float]:
        return {
            "skill_overlap": self.match_weight_skill_overlap,
            "requirement_coverage": self.match_weight_requirement_coverage,
            "semantic_similarity": self.match_weight_semantic_similarity,
            "experience": self.match_weight_experience,
        }

    @property
    def llm_is_configured(self) -> bool:
        """An OpenAI-compatible provider needs a key unless it is a local server."""
        if self.llm_provider != "openai_compatible":
            return False
        is_local = any(h in self.llm_base_url for h in ("localhost", "127.0.0.1", "ollama"))
        return bool(self.llm_api_key.get_secret_value()) or is_local


@lru_cache
def get_settings() -> Settings:
    return Settings()
