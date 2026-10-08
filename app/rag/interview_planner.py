"""Deterministic planning of the next interview question.

Before calling the LLM we decide *what* to ask about: a category and a focus
(a skill, requirement or behavioral theme) taken from the match analysis. This
is what makes questions varied and personalised: the LLM is not asked "write
an interview question" but "write a GAP question about Kubernetes, which the
job requires and the CV does not mention, given this retrieved context".
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.models.schemas import MatchReport

# Rotation order: start with the candidate's strengths (confidence), then
# probe experience, then a gap, then soft skills.
CATEGORY_ROTATION = ["technical", "experience", "gap", "behavioral"]

BEHAVIORAL_THEMES = [
    "collaborating with cross-functional stakeholders (product, business, design)",
    "handling a project that failed or did not go as planned",
    "explaining complex technical results to a non-technical audience",
    "prioritising competing tasks under a tight deadline",
    "mentoring or helping a colleague grow",
    "disagreeing with a teammate or manager on a technical decision",
]


@dataclass
class PlannedQuestion:
    category: str
    focus: str
    retrieval_query: str


@dataclass
class InterviewPlanner:
    match: MatchReport
    used_focus: set[str] = field(default_factory=set)
    turn: int = 0

    def _available_categories(self) -> list[str]:
        has_gap = bool(self.match.missing_skills) or any(r.status != "covered" for r in self.match.requirements)
        return [c for c in CATEGORY_ROTATION if c != "gap" or has_gap]

    def next(self, category: str | None = None) -> PlannedQuestion:
        categories = self._available_categories()
        if category is None or (category == "gap" and "gap" not in categories):
            category = categories[self.turn % len(categories)]
        self.turn += 1
        focus = self._pick_focus(category)
        self.used_focus.add(focus)
        return PlannedQuestion(category=category, focus=focus, retrieval_query=self._query(category, focus))

    def _first_unused(self, options: list[str], fallback: str) -> str:
        for option in options:
            if option not in self.used_focus:
                return option
        return options[self.turn % len(options)] if options else fallback

    def _pick_focus(self, category: str) -> str:
        m = self.match
        if category == "technical":
            required = [s.name for s in m.matching_skills if s.category not in ("Soft skills", "Languages")]
            return self._first_unused(required or [s.name for s in m.missing_skills], "the main technologies of the role")
        if category == "gap":
            missing = [s.name for s in m.missing_skills if s.importance == "required"]
            missing += [s.name for s in m.missing_skills if s.importance == "preferred"]
            missing += [r.text for r in m.requirements if r.status == "missing"]
            missing += [r.text for r in m.requirements if r.status == "partial"]
            return self._first_unused(missing, "an area of the job that is new to you")
        if category == "experience":
            reqs = [r.text for r in m.requirements if r.status == "covered" and r.kind == "required"]
            reqs += [r.text for r in m.requirements if r.status == "partial"]
            return self._first_unused(reqs or [r.text for r in m.requirements], "your most relevant experience")
        return self._first_unused(BEHAVIORAL_THEMES, BEHAVIORAL_THEMES[0])

    @staticmethod
    def _query(category: str, focus: str) -> str:
        # The query wording steers retrieval toward the right kind of evidence.
        if category == "behavioral":
            return f"teamwork, communication, stakeholders, responsibilities: {focus}"
        if category == "gap":
            return f"{focus} requirement; related or transferable experience"
        return f"experience with {focus}"
