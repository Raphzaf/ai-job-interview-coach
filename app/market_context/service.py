"""Market context: how often the market asks for the skills of this job.

This is where the two halves of the project meet. The data-analytics layer
(ingestion -> PostgreSQL -> validated extracts) measured, for 667,989 data/tech
postings from 2023, the share of postings asking for each skill per role family.
`python -m market.coach_context` turns that into a 12 KB JSON file shipped with
the app, so the coach can say "AWS is missing from your CV, and 38.6 % of Data
Engineer postings ask for it" without a database and without network access.

The market context is informational only: it never changes the match score.
It is shown only when the job title maps to one of the 7 role families covered
by the dataset; for any other job (e.g. marketing) nothing is shown rather than
misleading data-role statistics.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from app.core.logging import get_logger
from app.models.schemas import MarketContext, MatchReport, SkillDemand

logger = get_logger(__name__)

DEFAULT_FILE = Path(__file__).with_name("skill_demand_2023.json")
TOP_SKILLS = 10

# Title keywords -> role family of the reference dataset. Order matters: the
# specific titles are tested before the generic ones ("data engineer" before
# "engineer"). Only the job TITLE is used: a description saying "you will work
# with data scientists" must not turn a backend job into a data-science job.
ROLE_PATTERNS: list[tuple[str, str]] = [
    ("Machine Learning Engineer", r"machine learning engineer|\bml engineer|mlops|\bai engineer|\bllm engineer"),
    ("Data Engineer", r"data engineer|analytics engineer|\betl developer|big data engineer"),
    ("Data Scientist", r"data scientist|\bdata science\b"),
    ("Data Analyst", r"data analyst|\bbi analyst|business intelligence|reporting analyst|analytics analyst"),
    ("Business Analyst", r"business analyst"),
    ("Cloud Engineer", r"cloud engineer|cloud architect|devops|site reliability|\bsre\b|platform engineer"),
    ("Software Engineer", r"software engineer|software developer|backend|back-end|frontend|front-end|"
                          r"full[- ]?stack|web developer|python developer|java developer"),
]
_COMPILED = [(role, re.compile(pattern, re.IGNORECASE)) for role, pattern in ROLE_PATTERNS]


def job_title(job_text: str) -> str:
    """The first non-empty line of a job description is, in practice, its title."""
    for line in job_text.splitlines():
        if line.strip():
            return line.strip()[:150]
    return ""


def detect_role_family(title: str) -> str | None:
    for role, pattern in _COMPILED:
        if pattern.search(title):
            return role
    return None


class MarketContextService:
    def __init__(self, data: dict):
        self.data = data
        self.source = f"{data['source']}, {data['period']} ({data['population']})"

    @classmethod
    def load(cls, path: Path = DEFAULT_FILE) -> "MarketContextService | None":
        """Load the context file; the coach works without it (returns None)."""
        try:
            return cls(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, KeyError) as exc:
            logger.warning("Market context unavailable (%s): %s", path, exc)
            return None

    def build(self, job_text: str, job_name: str, match: MatchReport) -> MarketContext:
        title = job_title(job_text)
        role = detect_role_family(title) or detect_role_family(job_name)
        if role is None:
            return MarketContext(
                available=False, job_title=title, source=self.source,
                note="No market figures for this job: its title does not match one of the data/tech role "
                     "families covered by the reference dataset (" + ", ".join(sorted(self.data["roles"])) + ").",
            )

        stats = self.data["roles"][role]
        postings = stats["postings"]
        candidate = {s.name for s in match.matching_skills} | {s.name for s in match.additional_skills}
        job_skills = {s.name for s in match.matching_skills} | {s.name for s in match.missing_skills}

        def demand(skill: str) -> SkillDemand:
            n = stats["skills"].get(skill, 0)
            return SkillDemand(skill=skill, share=round(100 * n / postings, 1), postings_with_skill=n,
                               in_cv=skill in candidate, in_job=skill in job_skills)

        missing = [s.name for s in match.missing_skills]
        tracked = [s for s in missing if s in stats["skills"]]
        return MarketContext(
            available=True,
            role_family=role,
            job_title=title,
            source=self.source,
            postings=postings,
            missing_skill_demand=sorted((demand(s) for s in tracked), key=lambda d: d.share, reverse=True),
            untracked_missing_skills=[s for s in missing if s not in stats["skills"]],
            top_skills=[demand(s) for s in list(stats["skills"])[:TOP_SKILLS]],
            note=f"Share of {postings:,} {role} postings (2023) that list each skill. Market data is context "
                 "only: it does not change the match score, and 2023 demand may differ from today's.",
        )
