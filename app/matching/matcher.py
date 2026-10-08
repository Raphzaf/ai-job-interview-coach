"""Transparent CV / job match scoring.

The overall score is NOT produced by the LLM. It is a weighted average of four
deterministic signals, each in [0, 1], each explained in the UI:

| signal               | default weight | why                                                                 |
|----------------------|----------------|---------------------------------------------------------------------|
| skill_overlap        | 0.40           | Most explicit & verifiable signal; what recruiters/ATS screen on.   |
| requirement_coverage | 0.35           | Semantic: catches requirements phrased beyond keywords, via FAISS.  |
| semantic_similarity  | 0.15           | Holistic document similarity; useful but coarse, so a low weight.   |
| experience           | 0.10           | Years are a crude proxy for seniority; low weight avoids over-      |
|                      |                | penalising career changers.                                         |

Signals that cannot be computed (e.g. the job states no years of experience)
are marked "not applicable" and the remaining weights are re-normalised, so a
missing signal neither helps nor hurts the candidate.

Calibration: all-MiniLM-L6-v2 cosine similarities are not percentages
(unrelated professional texts still score ~0.2-0.4). The anchors below were
chosen from the evaluation set in evaluation/data (3 CVs x 3 jobs): matching
pairs had document similarity ~0.78-0.83, mismatched pairs ~0.39-0.68.

The result is an estimate of document fit, not a hiring probability.
"""

from __future__ import annotations

import numpy as np

from app.matching.requirements import Requirement, candidate_years, extract_requirements, required_years
from app.matching.skills import alternative_groups, expand_implied, extract_skills, skill_category
from app.models.domain import Document, RetrievedChunk, SkillMatch
from app.models.schemas import (
    ExperienceInfo,
    MatchReport,
    RequirementCoverage,
    ScoreComponent,
    SkillItem,
    SourceChunk,
)
from app.retrieval.retriever import Retriever

DEFAULT_WEIGHTS = {
    "skill_overlap": 0.40,
    "requirement_coverage": 0.35,
    "semantic_similarity": 0.15,
    "experience": 0.10,
}
# A preferred ("nice to have") skill/requirement counts half as much as a required one.
PREFERRED_WEIGHT = 0.5
# Document-level cosine similarity -> [0, 1] (see calibration note above).
DOC_SIM_LOW, DOC_SIM_HIGH = 0.45, 0.85
# Requirement-to-best-CV-chunk cosine similarity -> [0, 1].
REQ_SIM_LOW, REQ_SIM_HIGH = 0.25, 0.55
# Coverage thresholds used for the covered / partial / missing labels.
COVERED_AT, PARTIAL_AT = 0.70, 0.35

# Evidence selection = light hybrid retrieval. We take the top semantic CV
# chunks and re-rank them: chunks that literally mention the requirement's
# skills first, experience over a bare skills list, then cosine similarity.
# Observed on the sample CV: for "Experience with vector databases (FAISS...)"
# MiniLM ranked a loosely related project line above the bullet that actually
# says "FAISS" (cosine 0.34 vs 0.23), whatever the chunk size.
EVIDENCE_CANDIDATES = 5

DISCLAIMER = (
    "This score estimates how well the CV text matches the job description using skill overlap, "
    "requirement coverage, semantic similarity and years of experience. It is not a hiring "
    "probability and cannot judge qualities that are absent from the documents."
)


def rescale(value: float, low: float, high: float) -> float:
    """Linear rescale of `value` from [low, high] to [0, 1], clipped."""
    return float(np.clip((value - low) / (high - low), 0.0, 1.0))


def to_source(result: RetrievedChunk) -> SourceChunk:
    c = result.chunk
    return SourceChunk(
        chunk_id=c.chunk_id, doc_type=c.doc_type, section=c.section or "General",
        label=c.source_label, text=c.text, score=round(result.score, 3),
    )


def _evidence_rank(result: RetrievedChunk, skills: list[str]) -> tuple[int, bool, float]:
    present = set(extract_skills(result.chunk.text))
    mentions = sum(s in present for s in skills)
    return mentions, "skill" not in result.chunk.section.lower(), result.score


def compare_skills(cv_text: str, job_text: str, requirements: list[Requirement]) -> SkillMatch:
    job_skills = extract_skills(job_text)
    # Implied skills (e.g. RAG => Generative AI) count as present in the CV.
    cv_skills = expand_implied(extract_skills(cv_text))
    # A skill is "preferred" only if it appears exclusively in nice-to-have requirements.
    preferred_text = "\n".join(r.text for r in requirements if r.kind == "preferred")
    required_text_skills = set(extract_skills("\n".join(r.text for r in requirements if r.kind == "required")))
    preferred = [s for s in extract_skills(preferred_text) if s not in required_text_skills]
    # "PyTorch or TensorFlow": if the CV has one alternative, the others are not gaps.
    satisfied_alternatives = {
        skill
        for req in requirements
        for group in alternative_groups(req.text)
        if group & cv_skills
        for skill in group - cv_skills
    }
    job_skills = [s for s in job_skills if s not in satisfied_alternatives]
    preferred = [s for s in preferred if s not in satisfied_alternatives]
    required = [s for s in job_skills if s not in preferred]
    return SkillMatch(
        required=required,
        preferred=preferred,
        candidate=sorted(cv_skills),
        matched_required=[s for s in required if s in cv_skills],
        matched_preferred=[s for s in preferred if s in cv_skills],
        missing_required=[s for s in required if s not in cv_skills],
        missing_preferred=[s for s in preferred if s not in cv_skills],
        additional=[s for s in extract_skills(cv_text) if s not in job_skills and s not in satisfied_alternatives],
        implied=sorted(cv_skills - set(extract_skills(cv_text))),
    )


class Matcher:
    def __init__(self, weights: dict[str, float] | None = None):
        weights = weights or DEFAULT_WEIGHTS
        unknown = set(weights) - set(DEFAULT_WEIGHTS)
        if unknown:
            raise ValueError(f"Unknown weight keys: {unknown}")
        if any(w < 0 for w in weights.values()) or sum(weights.values()) <= 0:
            raise ValueError("Weights must be non-negative and not all zero")
        self.weights = {k: float(weights.get(k, 0.0)) for k in DEFAULT_WEIGHTS}

    # --- individual signals ---------------------------------------------------

    @staticmethod
    def skill_overlap_score(skills: SkillMatch) -> float | None:
        total = len(skills.required) + PREFERRED_WEIGHT * len(skills.preferred)
        if total == 0:
            return None
        matched = len(skills.matched_required) + PREFERRED_WEIGHT * len(skills.matched_preferred)
        return matched / total

    @staticmethod
    def experience_score(required: int | None, candidate: float | None) -> float | None:
        if required is None or candidate is None:
            return None
        return min(1.0, candidate / required) if required > 0 else 1.0

    def requirement_coverage(
        self, requirements: list[Requirement], retriever: Retriever, cv_skills: set[str]
    ) -> list[RequirementCoverage]:
        """For each requirement, find the best CV evidence with FAISS (semantic search).

        Coverage = max(semantic credit, skill credit). The skill credit makes
        sure an explicit keyword match ("Docker" in both) is not lost when the
        surrounding sentences happen to be phrased very differently.
        """
        results: list[RequirementCoverage] = []
        for req in requirements:
            # Alternatives the CV already satisfies ("FastAPI or Flask") are not counted as missing.
            satisfied = {s for g in alternative_groups(req.text) if g & cv_skills for s in g - cv_skills}
            req_skills = [s for s in extract_skills(req.text) if s not in satisfied]
            matched = [s for s in req_skills if s in cv_skills]
            hits = retriever.retrieve(req.text, k=EVIDENCE_CANDIDATES, doc_type="cv")
            best = max(hits, key=lambda h: _evidence_rank(h, matched), default=None)
            # The coverage uses the best *semantic* similarity; the rerank only
            # chooses which chunk is displayed as evidence.
            similarity = hits[0].score if hits else 0.0
            semantic_credit = rescale(similarity, REQ_SIM_LOW, REQ_SIM_HIGH)
            skill_credit = len(matched) / len(req_skills) if req_skills else 0.0
            coverage = max(semantic_credit, skill_credit)
            status = "covered" if coverage >= COVERED_AT else "partial" if coverage >= PARTIAL_AT else "missing"
            results.append(
                RequirementCoverage(
                    text=req.text, kind=req.kind, status=status, coverage=round(coverage * 100, 1),
                    similarity=round(similarity, 3), matched_skills=matched,
                    missing_skills=[s for s in req_skills if s not in cv_skills],
                    evidence=to_source(best) if best and coverage >= PARTIAL_AT else None,
                )
            )
        return results

    @staticmethod
    def coverage_score(coverages: list[RequirementCoverage]) -> float | None:
        if not coverages:
            return None
        weights = [1.0 if c.kind == "required" else PREFERRED_WEIGHT for c in coverages]
        return sum(w * c.coverage / 100 for w, c in zip(weights, coverages)) / sum(weights)

    @staticmethod
    def document_similarity(retriever: Retriever) -> tuple[float | None, float | None]:
        """Cosine similarity between the mean CV vector and the mean job vector."""
        cv_vectors = retriever.store.vectors_for("cv")
        job_vectors = retriever.store.vectors_for("job")
        if len(cv_vectors) == 0 or len(job_vectors) == 0:
            return None, None
        cv_centroid, job_centroid = cv_vectors.mean(axis=0), job_vectors.mean(axis=0)
        denom = float(np.linalg.norm(cv_centroid) * np.linalg.norm(job_centroid)) or 1.0
        cosine = float(cv_centroid @ job_centroid) / denom
        return cosine, rescale(cosine, DOC_SIM_LOW, DOC_SIM_HIGH)

    def combine(self, signals: dict[str, float | None]) -> tuple[float, dict[str, float]]:
        """Weighted average over applicable signals; weights re-normalised to sum to 1."""
        applicable = {k: v for k, v in signals.items() if v is not None and self.weights[k] > 0}
        total_weight = sum(self.weights[k] for k in applicable)
        if total_weight == 0:
            return 0.0, {k: 0.0 for k in signals}
        effective = {k: (self.weights[k] / total_weight if k in applicable else 0.0) for k in signals}
        overall = sum(effective[k] * applicable[k] for k in applicable)
        return overall, effective

    # --- full analysis --------------------------------------------------------

    def analyze(self, cv: Document, job: Document, retriever: Retriever) -> MatchReport:
        requirements = extract_requirements(job.text)
        skills = compare_skills(cv.text, job.text, requirements)
        coverages = self.requirement_coverage(requirements, retriever, set(skills.candidate))
        doc_cosine, doc_score = self.document_similarity(retriever)
        req_years, cand_years = required_years(job.text), candidate_years(cv.text)

        signals = {
            "skill_overlap": self.skill_overlap_score(skills),
            "requirement_coverage": self.coverage_score(coverages),
            "semantic_similarity": doc_score,
            "experience": self.experience_score(req_years, cand_years),
        }
        overall, effective = self.combine(signals)
        n_covered = sum(c.status == "covered" for c in coverages)
        n_partial = sum(c.status == "partial" for c in coverages)
        explanations = {
            "skill_overlap": (
                f"{len(skills.matched_required)}/{len(skills.required)} required and "
                f"{len(skills.matched_preferred)}/{len(skills.preferred)} preferred job skills found in the CV "
                f"(preferred skills count x{PREFERRED_WEIGHT})."
            ),
            "requirement_coverage": (
                f"{n_covered} covered, {n_partial} partially covered out of {len(coverages)} requirements, "
                "using semantic search for CV evidence of each requirement."
            ),
            "semantic_similarity": (
                f"Cosine similarity of the average CV and job embeddings: {doc_cosine:.2f} "
                f"(rescaled from [{DOC_SIM_LOW}, {DOC_SIM_HIGH}] to 0-100%)."
                if doc_cosine is not None else "Not enough content to compare."
            ),
            "experience": (
                f"Job asks for {req_years}+ years; about {cand_years} years computed from the CV's dates."
                if signals["experience"] is not None
                else "Not applicable: " + ("the job states no minimum years." if req_years is None
                                           else "no employment date ranges were found in the CV.")
            ),
        }
        labels = {
            "skill_overlap": "Skills", "requirement_coverage": "Requirements",
            "semantic_similarity": "Semantic similarity", "experience": "Experience",
        }
        breakdown = [
            ScoreComponent(
                key=key, label=labels[key], score=round((value or 0.0) * 100, 1),
                weight=round(effective[key], 3), applicable=value is not None, explanation=explanations[key],
            )
            for key, value in signals.items()
        ]

        return MatchReport(
            overall_score=round(overall * 100, 1),
            breakdown=breakdown,
            matching_skills=[
                SkillItem(name=s, category=skill_category(s), importance="required", implied=s in skills.implied)
                for s in skills.matched_required
            ]
            + [
                SkillItem(name=s, category=skill_category(s), importance="preferred", implied=s in skills.implied)
                for s in skills.matched_preferred
            ],
            missing_skills=[SkillItem(name=s, category=skill_category(s), importance="required") for s in skills.missing_required]
            + [SkillItem(name=s, category=skill_category(s), importance="preferred") for s in skills.missing_preferred],
            additional_skills=[SkillItem(name=s, category=skill_category(s), importance="candidate") for s in skills.additional],
            requirements=coverages,
            experience=ExperienceInfo(required_years=req_years, candidate_years=cand_years),
            relevant_experience=self._relevant_experience(coverages),
            strengths=self._strengths(skills, coverages, req_years, cand_years),
            gaps=self._gaps(skills, coverages, req_years, cand_years),
            disclaimer=DISCLAIMER,
        )

    @staticmethod
    def _relevant_experience(coverages: list[RequirementCoverage], limit: int = 4) -> list[SourceChunk]:
        """The CV chunks most often/most strongly retrieved as evidence for job requirements."""
        best: dict[str, SourceChunk] = {}
        for c in coverages:
            if c.evidence and (c.evidence.chunk_id not in best or c.evidence.score > best[c.evidence.chunk_id].score):
                best[c.evidence.chunk_id] = c.evidence
        return sorted(best.values(), key=lambda s: s.score, reverse=True)[:limit]

    @staticmethod
    def _strengths(skills: SkillMatch, coverages, req_years, cand_years) -> list[str]:
        out: list[str] = []
        if skills.matched_required:
            out.append("Has required skills: " + ", ".join(skills.matched_required[:8]) + ".")
        covered = [c for c in coverages if c.status == "covered" and c.kind == "required"]
        for c in covered[:3]:
            out.append(f"Covers requirement: “{c.text}”.")
        if req_years and cand_years and cand_years >= req_years:
            out.append(f"Meets the experience level ({cand_years} years vs {req_years}+ requested).")
        if skills.matched_preferred:
            out.append("Also brings nice-to-have skills: " + ", ".join(skills.matched_preferred) + ".")
        return out

    @staticmethod
    def _gaps(skills: SkillMatch, coverages, req_years, cand_years) -> list[str]:
        out: list[str] = []
        if skills.missing_required:
            out.append("Required skills not found in the CV: " + ", ".join(skills.missing_required) + ".")
        for c in [c for c in coverages if c.status == "missing" and c.kind == "required"][:3]:
            out.append(f"No clear CV evidence for: “{c.text}”.")
        if req_years and cand_years is not None and cand_years < req_years:
            out.append(f"Experience below the requested level ({cand_years} vs {req_years}+ years).")
        if skills.missing_preferred:
            out.append("Nice-to-have skills not mentioned: " + ", ".join(skills.missing_preferred) + ".")
        return out
