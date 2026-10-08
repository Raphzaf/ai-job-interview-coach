"""Feature engineering on documents: job requirements and years of experience.

These hand-crafted features complement embeddings: they turn free text into
explicit, countable signals (a list of requirements, a number of years) that
the transparent match score is built from.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from app.document_processing.chunker import split_sections

_REQUIREMENT_SECTION_KEYWORDS = (
    "requirement", "qualification", "looking for", "who you are", "must", "nice to have",
    "nice-to-have", "preferred", "bonus", "profile", "skills", "you have", "experience",
)
_PREFERRED_KEYWORDS = ("nice to have", "nice-to-have", "preferred", "bonus", "a plus", "ideally", "is a plus", "desirable")


@dataclass(frozen=True)
class Requirement:
    text: str
    kind: str  # "required" | "preferred"


def extract_requirements(job_text: str) -> list[Requirement]:
    """Extract the individual requirements (bullets) of a job description.

    Priority: bullets inside requirement-like sections -> any bullet in the
    document -> sentences. The fallbacks keep the feature usable for job ads
    written as plain prose.
    """
    sections = split_sections(job_text)
    requirements: list[Requirement] = []
    for section in sections:
        title = section.title.lower()
        if not any(k in title for k in _REQUIREMENT_SECTION_KEYWORDS):
            continue
        section_preferred = any(k in title for k in _PREFERRED_KEYWORDS)
        for unit in section.units:
            text = unit.removeprefix("- ").strip()
            if len(text) < 8:
                continue
            preferred = section_preferred or any(k in text.lower() for k in _PREFERRED_KEYWORDS)
            requirements.append(Requirement(text=text, kind="preferred" if preferred else "required"))

    if not requirements:
        units = [u for s in sections for u in s.units]
        bullets = [u.removeprefix("- ").strip() for u in units if u.startswith("- ")]
        candidates = bullets or [s.strip() for u in units for s in re.split(r"(?<=[.!?])\s+", u)]
        for text in candidates:
            if len(text) >= 15:
                kind = "preferred" if any(k in text.lower() for k in _PREFERRED_KEYWORDS) else "required"
                requirements.append(Requirement(text=text, kind=kind))
    # Cap to keep the analysis fast and the UI readable.
    return requirements[:25]


# --- Years of experience -------------------------------------------------------

_REQUIRED_YEARS_RE = re.compile(
    r"(\d{1,2})\s*\+?\s*(?:(?:-|–|to)\s*\d{1,2}\s*)?(?:years?|yrs?)\b(?:[^.\n]{0,40}?)\b(?:experience|exp\.?)",
    re.IGNORECASE,
)
_MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
_DATE = r"(?:(?P<{p}m>[A-Za-z]{{3,9}}\.?|\d{{1,2}})[ /.-]*)?(?P<{p}y>(?:19|20)\d{{2}})"
_RANGE_RE = re.compile(
    _DATE.format(p="s") + r"\s*(?:-|–|—|to|until)\s*(?:" + _DATE.format(p="e") + r"|(?P<present>present|current|now|today|ongoing))",
    re.IGNORECASE,
)
_EXPERIENCE_SECTION_KEYWORDS = ("experience", "employment", "work history", "career")
_EXCLUDED_SECTION_KEYWORDS = ("education", "certification", "training", "volunteer", "project")


def required_years(job_text: str) -> int | None:
    """Largest 'N+ years of experience' stated in the job description, if any."""
    values = [int(m.group(1)) for m in _REQUIRED_YEARS_RE.finditer(job_text)]
    values = [v for v in values if 0 < v <= 25]
    return max(values) if values else None


def _month(token: str | None, default: int) -> int:
    if not token:
        return default
    if token.isdigit():
        value = int(token)
        return value if 1 <= value <= 12 else default
    return _MONTHS.get(token[:3].lower(), default)


def candidate_years(cv_text: str, today: date | None = None) -> float | None:
    """Total professional experience computed from date ranges in the CV.

    Only date ranges inside experience-like sections are counted (education
    dates would inflate the number). Overlapping jobs are merged so two
    parallel positions are not counted twice. Returns None if no range is found.
    """
    today = today or date.today()
    sections = split_sections(cv_text)
    experience_sections = [s for s in sections if any(k in s.title.lower() for k in _EXPERIENCE_SECTION_KEYWORDS)]
    if not experience_sections:
        experience_sections = [s for s in sections if not any(k in s.title.lower() for k in _EXCLUDED_SECTION_KEYWORDS)]
    text = "\n".join(u for s in experience_sections for u in s.units)

    intervals: list[tuple[int, int]] = []
    for m in _RANGE_RE.finditer(text):
        start = int(m.group("sy")) * 12 + _month(m.group("sm"), 1) - 1
        if m.group("present"):
            end = today.year * 12 + today.month - 1
        else:
            end = int(m.group("ey")) * 12 + _month(m.group("em"), 12) - 1
        if start <= end <= today.year * 12 + today.month:
            intervals.append((start, end))
    if not intervals:
        return None
    intervals.sort()
    merged = [list(intervals[0])]
    for start, end in intervals[1:]:
        if start <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    months = sum(end - start + 1 for start, end in merged)
    return round(months / 12, 1)
