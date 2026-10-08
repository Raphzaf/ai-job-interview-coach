"""Internal domain objects shared by the pipeline stages.

These are plain dataclasses (not Pydantic) because they never cross the API
boundary directly: they carry data between preprocessing, embedding, FAISS and
the RAG pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

DocType = Literal["cv", "job"]

DOC_TYPE_LABELS: dict[str, str] = {"cv": "CV", "job": "Job description"}


@dataclass(frozen=True)
class Document:
    """A cleaned, validated source document."""

    doc_type: DocType
    name: str
    text: str


@dataclass(frozen=True)
class Chunk:
    """A retrievable piece of a document plus the metadata needed to trace it back.

    The metadata (document type/name, section, position) travels with the text
    all the way to the prompt and the UI, so every piece of retrieved context
    can be attributed to its source ("CV > Experience, chunk 3").
    """

    chunk_id: str
    doc_type: DocType
    doc_name: str
    section: str
    text: str
    position: int
    token_count: int

    @property
    def embedding_text(self) -> str:
        # Prefixing the section title gives the embedding model extra context:
        # "Skills: Python, SQL" is semantically clearer than "Python, SQL" alone.
        return f"{self.section}: {self.text}" if self.section else self.text

    @property
    def source_label(self) -> str:
        return f"{DOC_TYPE_LABELS[self.doc_type]} › {self.section or 'General'} (#{self.position})"


@dataclass(frozen=True)
class RetrievedChunk:
    """A chunk returned by FAISS together with its cosine similarity to the query."""

    chunk: Chunk
    score: float


@dataclass
class SkillMatch:
    """Skills of the job description split by whether the CV mentions them."""

    required: list[str] = field(default_factory=list)
    preferred: list[str] = field(default_factory=list)
    candidate: list[str] = field(default_factory=list)
    matched_required: list[str] = field(default_factory=list)
    matched_preferred: list[str] = field(default_factory=list)
    missing_required: list[str] = field(default_factory=list)
    missing_preferred: list[str] = field(default_factory=list)
    additional: list[str] = field(default_factory=list)
    # Skills not written in the CV but implied by a more specific one (RAG => Generative AI).
    implied: list[str] = field(default_factory=list)
