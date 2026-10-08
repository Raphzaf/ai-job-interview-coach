"""Token counting.

Why tokens and not characters? Transformer models do not see characters or
words, they see *tokens* from their own vocabulary (word-pieces for
all-MiniLM-L6-v2). Every model has a hard token limit: all-MiniLM-L6-v2 silently
TRUNCATES input beyond 256 tokens, so a chunk that is too long would be embedded
from its first part only and the rest would be invisible to retrieval.

We therefore measure chunk sizes with the *same tokenizer as the embedding
model*. The same counter is also used to keep the retrieved context sent to the
LLM within a fixed budget (an approximation, since the LLM's tokenizer differs,
but it is in the right order of magnitude and keeps prompts bounded).
"""

from __future__ import annotations

import re
from typing import Protocol

from app.core.logging import get_logger

logger = get_logger(__name__)


class TokenCounter(Protocol):
    name: str

    def count(self, text: str) -> int: ...


class HuggingFaceTokenCounter:
    """Exact token counts using the embedding model's own tokenizer."""

    def __init__(self, model_name: str):
        from transformers import AutoTokenizer

        self.name = model_name
        self._tokenizer = AutoTokenizer.from_pretrained(model_name)

    def count(self, text: str) -> int:
        # add_special_tokens=False: we count content tokens; the [CLS]/[SEP]
        # overhead is covered by the safety margin in CHUNK_MAX_TOKENS.
        return len(self._tokenizer.encode(text, add_special_tokens=False))


class ApproximateTokenCounter:
    """Dependency-free estimate (≈ word-pieces) used in tests and hashing mode.

    Word-piece tokenizers emit one token per punctuation mark and split rare
    words into several pieces, so we count words + punctuation and add ~15%.
    """

    name = "approximate"
    _WORD_RE = re.compile(r"\w+|[^\w\s]")

    def count(self, text: str) -> int:
        pieces = self._WORD_RE.findall(text)
        return int(round(len(pieces) * 1.15)) if pieces else 0


def build_token_counter(embedding_provider: str, model_name: str) -> TokenCounter:
    if embedding_provider == "sentence_transformers":
        try:
            return HuggingFaceTokenCounter(model_name)
        except Exception as exc:  # model download / offline problems
            logger.warning("Falling back to approximate token counting: %s", exc)
    return ApproximateTokenCounter()
