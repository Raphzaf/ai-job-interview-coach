"""Pydantic schemas.

Two families:
1. **LLM output schemas** (MatchInsights, InterviewQuestion, AnswerEvaluation):
   the LLM is asked to return JSON matching these; anything that does not
   validate is rejected (see app/rag/llm.py), never silently accepted.
2. **API schemas**: request/response bodies of the FastAPI endpoints.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

QuestionCategory = Literal["technical", "experience", "behavioral", "gap"]
GeneratedBy = Literal["llm", "offline", "offline-fallback"]


def _clean_list(items: list[str], max_items: int) -> list[str]:
    """Drop blanks/duplicates and cap length: LLMs sometimes pad lists with empty strings."""
    seen: dict[str, None] = {}
    for item in items:
        text = str(item).strip()
        if text and text.lower() not in (k.lower() for k in seen):
            seen[text] = None
    return list(seen)[:max_items]


# =============================================================================
# LLM output schemas
# =============================================================================


class MatchInsights(BaseModel):
    """Narrative part of the match analysis (scores are computed in code, not by the LLM)."""

    summary: str = Field(min_length=20, max_length=1200)
    strengths: list[str] = Field(min_length=1)
    gaps: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(min_length=1)

    @field_validator("strengths", "gaps", "recommendations")
    @classmethod
    def _cap(cls, v: list[str]) -> list[str]:
        return _clean_list(v, 6)


class InterviewQuestion(BaseModel):
    question: str = Field(min_length=15, max_length=600)
    category: QuestionCategory
    difficulty: Literal["easy", "medium", "hard"]
    focus: str = Field(min_length=2, max_length=120, description="Skill or topic the question targets")
    rationale: str = Field(min_length=10, max_length=600, description="Why this question for THIS candidate/job")
    expected_points: list[str] = Field(min_length=1, description="What a strong answer should cover")

    @field_validator("expected_points")
    @classmethod
    def _cap(cls, v: list[str]) -> list[str]:
        cleaned = _clean_list(v, 5)
        if not cleaned:
            raise ValueError("expected_points must contain at least one non-empty item")
        return cleaned


class CriteriaScores(BaseModel):
    """Each criterion is scored 0-10 against an explicit rubric (see prompts.py)."""

    relevance: int = Field(ge=0, le=10)
    specificity: int = Field(ge=0, le=10)
    structure: int = Field(ge=0, le=10)
    job_alignment: int = Field(ge=0, le=10)


class AnswerEvaluation(BaseModel):
    criteria: CriteriaScores
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    missing_points: list[str] = Field(default_factory=list)
    improvement_suggestions: list[str] = Field(min_length=1)
    improved_answer: str = Field(min_length=20, max_length=2500)
    grounding_note: str = Field(
        default="",
        max_length=600,
        description="Which parts rely on the CV/job documents vs. general interview advice",
    )

    @field_validator("strengths", "weaknesses", "missing_points", "improvement_suggestions")
    @classmethod
    def _cap(cls, v: list[str]) -> list[str]:
        return _clean_list(v, 6)

    @property
    def overall_score(self) -> float:
        # The overall score is computed in code as the mean of the rubric
        # criteria rather than asked from the LLM: it stays consistent with the
        # detailed scores and cannot be "inflated" independently.
        c = self.criteria
        return round((c.relevance + c.specificity + c.structure + c.job_alignment) / 4, 1)


# =============================================================================
# API schemas
# =============================================================================


class SourceChunk(BaseModel):
    """A retrieved chunk shown to the user as the source of an AI output."""

    chunk_id: str
    doc_type: Literal["cv", "job"]
    section: str
    label: str
    text: str
    score: float = Field(description="Cosine similarity between the query and this chunk")


class ExtractResponse(BaseModel):
    filename: str
    characters: int
    text: str


class AnalyzeRequest(BaseModel):
    cv_text: str = Field(min_length=1, description="CV text (pasted or extracted from a file)")
    job_text: str = Field(min_length=1, description="Job description text")
    cv_name: str = Field("cv", max_length=200)
    job_name: str = Field("job_description", max_length=200)


class ScoreComponent(BaseModel):
    key: str
    label: str
    score: float = Field(ge=0, le=100)
    weight: float = Field(ge=0, le=1, description="Effective weight after re-normalisation")
    applicable: bool
    explanation: str


class SkillItem(BaseModel):
    name: str
    category: str
    importance: Literal["required", "preferred", "candidate"]
    implied: bool = Field(False, description="Not written in the CV but implied by a more specific CV skill")


class RequirementCoverage(BaseModel):
    text: str
    kind: Literal["required", "preferred"]
    status: Literal["covered", "partial", "missing"]
    coverage: float = Field(ge=0, le=100)
    similarity: float
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    evidence: SourceChunk | None = None


class ExperienceInfo(BaseModel):
    required_years: int | None
    candidate_years: float | None


class MatchReport(BaseModel):
    overall_score: float = Field(ge=0, le=100)
    breakdown: list[ScoreComponent]
    matching_skills: list[SkillItem]
    missing_skills: list[SkillItem]
    additional_skills: list[SkillItem]
    requirements: list[RequirementCoverage]
    experience: ExperienceInfo
    relevant_experience: list[SourceChunk]
    strengths: list[str]
    gaps: list[str]
    disclaimer: str


class DocumentStats(BaseModel):
    doc_type: Literal["cv", "job"]
    name: str
    characters: int
    chunks: int
    total_tokens: int


class PipelineInfo(BaseModel):
    embedding_model: str
    embedding_dimension: int
    tokenizer: str
    index_type: str
    index_size: int
    llm: str


class AnalyzeResponse(BaseModel):
    session_id: str
    documents: list[DocumentStats]
    match: MatchReport
    insights: MatchInsights
    insights_generated_by: GeneratedBy
    insights_sources: list[SourceChunk]
    pipeline: PipelineInfo
    warnings: list[str] = Field(default_factory=list)


class QuestionRequest(BaseModel):
    session_id: str
    category: QuestionCategory | None = Field(
        None, description="Optional category; if omitted the coach rotates through categories"
    )


class QuestionResponse(BaseModel):
    session_id: str
    question_id: str
    question_number: int
    question: InterviewQuestion
    sources: list[SourceChunk]
    generated_by: GeneratedBy
    warnings: list[str] = Field(default_factory=list)


class AnswerRequest(BaseModel):
    session_id: str
    question_id: str
    answer: str = Field(min_length=1, max_length=6000)


class EvaluationResponse(BaseModel):
    session_id: str
    question_id: str
    score: float = Field(ge=0, le=10)
    evaluation: AnswerEvaluation
    sources: list[SourceChunk]
    generated_by: GeneratedBy
    warnings: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str
    llm_provider: str
    llm_model: str
    llm_configured: bool
    embedding_model: str
    active_sessions: int


class SampleDocuments(BaseModel):
    cv_name: str
    cv_text: str
    job_name: str
    job_text: str


class ErrorResponse(BaseModel):
    error: str
    message: str
