"""Text helpers for job descriptions (HTML -> text, language detection)."""

from __future__ import annotations

import html
import re

from app.document_processing.cleaner import clean_text

_BLOCK_TAGS = re.compile(r"</?(p|div|br|li|ul|ol|h[1-6]|tr|table|section)\b[^>]*>", re.IGNORECASE)
_TAGS = re.compile(r"<[^>]+>")

# Small, high-frequency function-word lists. Counting them is a transparent
# language heuristic that needs no extra dependency; it is only used to label
# descriptions as English/German so analyses can be stratified by language.
_EN = {"the", "and", "you", "with", "for", "our", "are", "will", "your", "we", "of", "to", "in", "is"}
_DE = {"und", "die", "der", "wir", "sie", "mit", "für", "ihre", "das", "zu", "bei", "eine", "ist", "auf"}
_WORD = re.compile(r"[a-zäöüß]+")


def html_to_text(raw_html: str) -> str:
    """Strip HTML while keeping paragraph/list structure as line breaks."""
    text = _BLOCK_TAGS.sub("\n", raw_html or "")
    text = _TAGS.sub(" ", text)
    # Adjacent block tags ("</li><li>") would otherwise leave empty lines
    # between list items: one block = one line.
    text = re.sub(r"\n[ \t]*(?:\n[ \t]*)+", "\n", text)
    return clean_text(html.unescape(text))


def detect_language(text: str, min_hits: int = 5) -> str:
    """Return 'en', 'de' or 'unknown' from function-word counts."""
    words = _WORD.findall(text.lower())
    en = sum(w in _EN for w in words)
    de = sum(w in _DE for w in words)
    if max(en, de) < min_hits:
        return "unknown"
    return "en" if en >= de else "de"
