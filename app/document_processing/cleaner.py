"""Text cleaning, normalization and validation.

Design principle: clean *formatting noise* (PDF artefacts, odd whitespace,
bullet glyphs) but never *content*. We deliberately do NOT lowercase, strip
punctuation, remove stop-words or stem, because CV/job text is full of tokens
where those characters carry meaning: "C++", "C#", "Node.js", "5+ years",
"AWS-SAA", "M.Sc.". The embedding model handles casing and stop-words itself.
"""

from __future__ import annotations

import re
import unicodedata

from app.core.errors import DocumentError

# Bullet glyphs produced by Word/PDF exports. They are normalised to "- " so
# the chunker can recognise list items as natural chunk boundaries.
_BULLETS = "•●▪■◦‣∙○◆►✓✔➢➤*·"
_BULLET_RE = re.compile(rf"^\s*[{re.escape(_BULLETS)}]\s*", re.MULTILINE)
# A dash/en-dash used as a bullet at the start of a line.
_DASH_BULLET_RE = re.compile(r"^\s*[-–—]\s+", re.MULTILINE)
# "develop-\nment" -> "development" (hyphenation inserted by PDF line wrapping).
# Restricted to lowercase letters on both sides so "Front-\nEnd" style compound
# names and ranges like "2019-\n2021" are left alone.
_HYPHEN_BREAK_RE = re.compile(r"([a-z])-\n([a-z])")
_ZERO_WIDTH_RE = re.compile(r"[​‌‍⁠﻿]")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_INLINE_SPACE_RE = re.compile(r"[ \t ]+")
_MANY_NEWLINES_RE = re.compile(r"\n{3,}")


def clean_text(text: str) -> str:
    """Normalise raw extracted text while preserving all meaningful content."""
    # NFKC folds PDF ligatures ("ﬁ" -> "fi") and full-width characters into
    # their plain equivalents so that "ﬁnance" matches "finance".
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _ZERO_WIDTH_RE.sub("", text)
    text = _CONTROL_RE.sub(" ", text)
    text = _HYPHEN_BREAK_RE.sub(r"\1\2", text)
    text = _BULLET_RE.sub("- ", text)
    text = _DASH_BULLET_RE.sub("- ", text)
    text = _INLINE_SPACE_RE.sub(" ", text)
    lines = [line.strip() for line in text.split("\n")]
    text = "\n".join(lines)
    text = _MANY_NEWLINES_RE.sub("\n\n", text)
    return text.strip()


def validate_document(text: str, label: str, min_chars: int, max_chars: int) -> str:
    """Reject documents that cannot produce a meaningful analysis.

    Failing loudly here is intentional: an empty or garbage document would
    otherwise flow through embeddings and the LLM and produce a confident but
    meaningless analysis.
    """
    stripped = text.strip()
    if not stripped:
        raise DocumentError(f"The {label} is empty. Please provide its text or upload a file.")
    if len(stripped) < min_chars:
        raise DocumentError(
            f"The {label} is too short ({len(stripped)} characters). "
            f"Please provide the full document (at least {min_chars} characters)."
        )
    if len(stripped) > max_chars:
        raise DocumentError(
            f"The {label} is too long ({len(stripped):,} characters, limit {max_chars:,}). "
            "Please upload only the relevant document."
        )
    letters = sum(ch.isalpha() for ch in stripped)
    if letters / len(stripped) < 0.4:
        # Mostly digits/symbols usually means a broken extraction (e.g. encoded PDF fonts).
        raise DocumentError(
            f"The {label} does not contain enough readable text. The file may be corrupted or encoded."
        )
    return stripped


def normalize_for_matching(text: str) -> str:
    """Lower-cased copy used ONLY for keyword/skill matching, never for embeddings."""
    text = unicodedata.normalize("NFKC", text).lower()
    return _INLINE_SPACE_RE.sub(" ", text.replace("\n", " "))
