"""Section-aware, token-bounded chunking.

Strategy (and why):
1. **Split by section first.** CVs and job ads are strongly structured
   ("Experience", "Skills", "Requirements"...). A chunk never crosses a section
   boundary, so a chunk is about one topic and its section title can be stored
   as metadata and shown as the source of retrieved context.
2. **Split sections into natural units**: bullet points and paragraphs. A
   bullet like "- Built a RAG chatbot with FAISS" is the smallest meaningful
   piece of evidence in a CV, so we never cut through one unless it alone
   exceeds the token budget (then we fall back to sentences, then words).
3. **Greedily pack units up to CHUNK_MAX_TOKENS** (default 200, below the 256
   token limit of all-MiniLM-L6-v2). Small chunks give precise retrieval;
   too-small chunks lose context ("- 3 years" alone means nothing). ~200 tokens
   is roughly one job entry or one requirements block.
4. **Overlap whole units** (≈ CHUNK_OVERLAP_TOKENS) between consecutive chunks
   of the same section, so that information sitting at a chunk boundary is
   still retrievable with its neighbouring context.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.document_processing.tokenizer import TokenCounter
from app.models.domain import Chunk, DocType

# Headings commonly found in CVs and job descriptions. Matching is done on the
# lower-cased line without trailing ":".
KNOWN_HEADINGS = {
    # CV
    "summary", "profile", "professional summary", "about me", "objective",
    "experience", "work experience", "professional experience", "employment history",
    "education", "skills", "technical skills", "core skills", "key skills", "competencies",
    "projects", "personal projects", "key projects", "certifications", "certificates",
    "languages", "publications", "awards", "interests", "volunteering", "achievements",
    # Job description
    "about us", "about the company", "about the role", "the role", "job description",
    "role overview", "responsibilities", "key responsibilities", "what you will do",
    "what you'll do", "your mission", "requirements", "required qualifications",
    "qualifications", "minimum qualifications", "what we are looking for",
    "what we're looking for", "who you are", "must have", "must-have", "nice to have",
    "nice-to-have", "preferred qualifications", "bonus points", "benefits",
    "what we offer", "perks", "tech stack", "our stack", "location", "how to apply",
}

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")


@dataclass
class _Section:
    title: str
    units: list[str]


def is_heading(line: str) -> bool:
    """Heuristic heading detector for plain text extracted from CVs/job ads."""
    candidate = line.strip().rstrip(":").strip()
    if not candidate or len(candidate) > 60 or candidate.startswith("- "):
        return False
    lowered = candidate.lower()
    if lowered in KNOWN_HEADINGS:
        return True
    words = candidate.split()
    # Short ALL-CAPS lines ("PROFESSIONAL EXPERIENCE") are headings in most templates.
    letters = [c for c in candidate if c.isalpha()]
    return len(words) <= 5 and len(letters) >= 4 and all(c.isupper() for c in letters) and not candidate.endswith(".")


def split_sections(text: str) -> list[_Section]:
    """Group lines into sections and sections into units (bullets / paragraphs)."""
    sections: list[_Section] = [_Section(title="", units=[])]
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            sections[-1].units.append(" ".join(paragraph))
            paragraph.clear()

    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            flush_paragraph()
            continue
        if is_heading(line):
            flush_paragraph()
            sections.append(_Section(title=_format_title(line), units=[]))
        elif line.startswith("- "):
            # Each bullet is its own unit: it is usually one self-contained claim.
            flush_paragraph()
            sections[-1].units.append(line)
        else:
            paragraph.append(line)
    flush_paragraph()
    return [s for s in sections if s.units]


def _format_title(line: str) -> str:
    title = line.strip().rstrip(":").strip()
    return title.title() if title.isupper() else title


class Chunker:
    def __init__(self, token_counter: TokenCounter, max_tokens: int = 200, overlap_tokens: int = 30):
        if overlap_tokens >= max_tokens:
            raise ValueError("overlap_tokens must be smaller than max_tokens")
        self.counter = token_counter
        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens

    def chunk(self, text: str, doc_type: DocType, doc_name: str) -> list[Chunk]:
        chunks: list[Chunk] = []
        for section in split_sections(text):
            # Budget for the content: the section title is prepended when
            # embedding (see Chunk.embedding_text), so reserve tokens for it.
            budget = self.max_tokens - (self.counter.count(section.title + ": ") if section.title else 0)
            units = [piece for unit in section.units for piece in self._split_oversized(unit, budget)]
            for chunk_units in self._pack(units, budget):
                body = "\n".join(chunk_units)
                chunks.append(
                    Chunk(
                        chunk_id=f"{doc_type}-{len(chunks)}",
                        doc_type=doc_type,
                        doc_name=doc_name,
                        section=section.title,
                        text=body,
                        position=len(chunks),
                        token_count=self.counter.count(body),
                    )
                )
        return chunks

    def _pack(self, units: list[str], budget: int) -> list[list[str]]:
        """Greedy packing of units into chunks with unit-level overlap."""
        groups: list[list[str]] = []
        current: list[str] = []
        current_tokens = 0
        for unit in units:
            unit_tokens = self.counter.count(unit)
            # A plain paragraph right after a bullet list usually starts a new
            # entry ("Data Scientist - Orbis, 2020-2023" after the previous
            # job's bullets). Breaking here keeps each job/degree with its own
            # bullets instead of gluing the header to the previous entry.
            starts_new_entry = bool(current) and current[-1].startswith("- ") and not unit.startswith("- ")
            if starts_new_entry:
                groups.append(current)
                current, current_tokens = [], 0
            elif current and current_tokens + unit_tokens > budget:
                groups.append(current)
                # Carry the trailing units (up to the overlap budget) into the next chunk.
                overlap: list[str] = []
                overlap_tokens = 0
                for previous in reversed(current):
                    t = self.counter.count(previous)
                    if overlap_tokens + t > self.overlap_tokens or overlap_tokens + t + unit_tokens > budget:
                        break
                    overlap.insert(0, previous)
                    overlap_tokens += t
                current, current_tokens = overlap, overlap_tokens
            current.append(unit)
            current_tokens += unit_tokens
        if current:
            groups.append(current)
        return groups

    def _split_oversized(self, unit: str, budget: int) -> list[str]:
        """Split a single unit that alone exceeds the budget: sentences first, then words."""
        if self.counter.count(unit) <= budget:
            return [unit]
        pieces: list[str] = []
        for sentence in _SENTENCE_RE.split(unit):
            if self.counter.count(sentence) <= budget:
                pieces.append(sentence)
                continue
            words, window = sentence.split(), []
            for word in words:
                if window and self.counter.count(" ".join(window + [word])) > budget:
                    pieces.append(" ".join(window))
                    window = []
                window.append(word)
            if window:
                pieces.append(" ".join(window))
        return pieces
