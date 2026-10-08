"""Orchestrates the preprocessing stage: raw text -> clean Document -> chunks."""

from __future__ import annotations

from app.core.config import Settings
from app.core.logging import get_logger
from app.document_processing.chunker import Chunker
from app.document_processing.cleaner import clean_text, validate_document
from app.document_processing.tokenizer import TokenCounter
from app.models.domain import DOC_TYPE_LABELS, Chunk, Document, DocType

logger = get_logger(__name__)


class DocumentProcessor:
    def __init__(self, settings: Settings, token_counter: TokenCounter):
        self.settings = settings
        self.token_counter = token_counter
        self.chunker = Chunker(token_counter, settings.chunk_max_tokens, settings.chunk_overlap_tokens)

    def prepare(self, raw_text: str, doc_type: DocType, name: str) -> Document:
        cleaned = clean_text(raw_text or "")
        validated = validate_document(
            cleaned,
            label=DOC_TYPE_LABELS[doc_type],
            min_chars=self.settings.min_document_chars,
            max_chars=self.settings.max_document_chars,
        )
        return Document(doc_type=doc_type, name=name, text=validated)

    def chunk(self, document: Document) -> list[Chunk]:
        chunks = self.chunker.chunk(document.text, document.doc_type, document.name)
        logger.info(
            "Chunked %s into %d chunks (max %d tokens, tokenizer=%s)",
            document.doc_type, len(chunks), max((c.token_count for c in chunks), default=0),
            self.token_counter.name,
        )
        return chunks
