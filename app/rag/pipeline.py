"""The RAG pipeline: where retrieval meets generation.

    analyze():   documents -> clean -> chunk -> embed -> FAISS index
                 -> deterministic match scoring (uses FAISS for requirement evidence)
                 -> multi-query retrieval -> LLM insights (grounded, validated JSON)
    next_question(): plan (category + focus) -> query embedding -> FAISS top-k from
                 CV and job -> context -> LLM -> validated InterviewQuestion
    evaluate():  question + answer -> FAISS top-k -> context + rubric -> LLM
                 -> validated AnswerEvaluation (overall score computed in code)

Each LLM step has an explicit fallback to the offline generator (configurable),
and every result says which one produced it (generated_by).
"""

from __future__ import annotations

import time
import uuid
from typing import Callable, TypeVar

from app.core.config import Settings
from app.core.errors import CoachError, LLMError
from app.core.logging import get_logger
from app.core.sessions import AskedQuestion, Session, SessionStore
from app.document_processing.processor import DocumentProcessor
from app.embeddings.service import EmbeddingService
from app.matching.matcher import Matcher, to_source
from app.matching.requirements import extract_requirements
from app.models.domain import RetrievedChunk
from app.models.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    AnswerEvaluation,
    DocumentStats,
    EvaluationResponse,
    InterviewQuestion,
    MatchInsights,
    MatchReport,
    PipelineInfo,
    QuestionResponse,
)
from app.rag import prompts
from app.rag.interview_planner import InterviewPlanner
from app.rag.llm import LLMProvider, generate_structured
from app.rag.offline import OfflineGenerator
from app.retrieval.retriever import Retriever

logger = get_logger(__name__)
T = TypeVar("T")

# Chunks below this cosine similarity are considered unrelated to the query and
# are not sent to the LLM (less noise, fewer tokens, less over-interpretation).
MIN_CONTEXT_SCORE = 0.15


def dedupe(results: list[RetrievedChunk]) -> list[RetrievedChunk]:
    """Keep the best score per chunk and sort by relevance."""
    best: dict[str, RetrievedChunk] = {}
    for r in results:
        if r.chunk.chunk_id not in best or r.score > best[r.chunk.chunk_id].score:
            best[r.chunk.chunk_id] = r
    return sorted(best.values(), key=lambda r: r.score, reverse=True)


class CoachPipeline:
    def __init__(
        self,
        settings: Settings,
        processor: DocumentProcessor,
        embedder: EmbeddingService,
        llm: LLMProvider | None,
        sessions: SessionStore,
    ):
        self.settings = settings
        self.processor = processor
        self.embedder = embedder
        self.llm = llm
        self.sessions = sessions
        self.matcher = Matcher(settings.match_weights)
        self.offline = OfflineGenerator(embedder)

    @property
    def llm_label(self) -> str:
        return self.llm.name if self.llm else "offline mode (no LLM configured)"

    # ------------------------------------------------------------------ helpers

    def _generate(self, llm_call: Callable[[LLMProvider], T], offline_call: Callable[[], T]) -> tuple[T, str, list[str]]:
        """Run the LLM step, falling back to the offline generator if allowed."""
        if self.llm is None:
            return offline_call(), "offline", []
        try:
            return llm_call(self.llm), "llm", []
        except LLMError as exc:
            if not self.settings.llm_fallback_to_offline:
                raise
            logger.warning("LLM step failed, using offline fallback: %s", exc.message)
            return offline_call(), "offline-fallback", [f"{exc.message} A simpler offline result is shown instead."]

    def _context(self, results: list[RetrievedChunk]) -> tuple[str, list[RetrievedChunk]]:
        return prompts.format_context(results, self.processor.token_counter)

    # ------------------------------------------------------------------ analysis

    def analyze(self, request: AnalyzeRequest) -> AnalyzeResponse:
        started = time.perf_counter()
        # 1-2. Extraction already happened (upload endpoint); clean + validate.
        cv = self.processor.prepare(request.cv_text, "cv", request.cv_name)
        job = self.processor.prepare(request.job_text, "job", request.job_name)
        # 3. Chunk with token-aware, section-aware splitting.
        cv_chunks, job_chunks = self.processor.chunk(cv), self.processor.chunk(job)
        # 4-5. Embed all chunks and build ONE FAISS index per session (reused later).
        retriever = Retriever.from_chunks(self.embedder, cv_chunks + job_chunks, self.settings.retrieval_top_k)
        # 6. Deterministic, explainable match scoring.
        match = self.matcher.analyze(cv, job, retriever)
        # 7. RAG: retrieve context for the analysis and let the LLM explain it.
        insights, generated_by, warnings, used = self._insights(match, retriever, job.text)

        session = self.sessions.create(cv=cv, job=job, retriever=retriever, match=match, planner=InterviewPlanner(match))
        logger.info("Analysis %s done in %.2fs (score=%.1f, insights=%s)",
                    session.session_id, time.perf_counter() - started, match.overall_score, generated_by)
        return AnalyzeResponse(
            session_id=session.session_id,
            documents=[
                DocumentStats(doc_type=d.doc_type, name=d.name, characters=len(d.text), chunks=len(ch),
                              total_tokens=sum(c.token_count for c in ch))
                for d, ch in ((cv, cv_chunks), (job, job_chunks))
            ],
            match=match,
            insights=insights,
            insights_generated_by=generated_by,
            insights_sources=[to_source(r) for r in used],
            pipeline=PipelineInfo(
                embedding_model=self.embedder.model_name,
                embedding_dimension=self.embedder.dimension,
                tokenizer=self.processor.token_counter.name,
                index_type="FAISS IndexFlatIP (exact cosine similarity)",
                index_size=len(retriever.store),
                llm=self.llm_label,
            ),
            warnings=warnings,
        )

    def _insights(self, match: MatchReport, retriever: Retriever, job_text: str):
        # Multi-query retrieval: one query per job requirement. A single query
        # made of the whole job description would exceed the embedding model's
        # 256-token window and average away the individual requirements.
        requirements = [r.text for r in extract_requirements(job_text) if r.kind == "required"][:6]
        results: list[RetrievedChunk] = []
        for query in requirements or [job_text[:500]]:
            results += retriever.retrieve(query, k=2, doc_type="cv", min_score=MIN_CONTEXT_SCORE)
            results += retriever.retrieve(query, k=1, doc_type="job", min_score=MIN_CONTEXT_SCORE)
        context, used = self._context(dedupe(results))
        facts = {
            "overall_score": match.overall_score,
            "score_breakdown": {c.label: c.score for c in match.breakdown if c.applicable},
            "matching_skills": [s.name for s in match.matching_skills],
            "missing_required_skills": [s.name for s in match.missing_skills if s.importance == "required"],
            "missing_preferred_skills": [s.name for s in match.missing_skills if s.importance == "preferred"],
            "requirements": [{"requirement": r.text, "status": r.status} for r in match.requirements],
            "years_required": match.experience.required_years,
            "years_in_cv": match.experience.candidate_years,
        }
        insights, generated_by, warnings = self._generate(
            lambda llm: generate_structured(llm, prompts.GROUNDING_RULES, prompts.insights_prompt(facts, context), MatchInsights),
            lambda: self.offline.insights(match),
        )
        return insights, generated_by, warnings, used

    # ------------------------------------------------------------------ interview

    def next_question(self, session_id: str, category: str | None = None) -> QuestionResponse:
        session = self.sessions.get(session_id)
        plan = session.planner.next(category)
        # Balanced retrieval: evidence from BOTH the job (what is asked) and the CV (what the candidate did).
        results = session.retriever.retrieve_balanced(plan.retrieval_query, k_per_doc=3, min_score=MIN_CONTEXT_SCORE)
        context, used = self._context(results)
        previous = [q.question.question for q in session.questions.values()]

        def llm_call(llm: LLMProvider) -> InterviewQuestion:
            question = generate_structured(
                llm, prompts.GROUNDING_RULES,
                prompts.question_prompt(plan.category, plan.focus, context, previous), InterviewQuestion,
            )
            # The category is decided by the planner, not by the model.
            return question.model_copy(update={"category": plan.category})

        question, generated_by, warnings = self._generate(llm_call, lambda: self.offline.question(plan, results))
        question_id = uuid.uuid4().hex[:8]
        session.questions[question_id] = AskedQuestion(question_id=question_id, question=question, context=used)
        logger.info("Session %s: question %d (%s, %s)", session_id, len(session.questions), plan.category, generated_by)
        return QuestionResponse(
            session_id=session_id, question_id=question_id, question_number=len(session.questions),
            question=question, sources=[to_source(r) for r in used], generated_by=generated_by, warnings=warnings,
        )

    def evaluate(self, session_id: str, question_id: str, answer: str) -> EvaluationResponse:
        session = self._session_with_question(session_id, question_id)
        asked = session.questions[question_id]
        answer = answer.strip()
        # Retrieve with question + answer: finds CV evidence the candidate could
        # have used, and the job requirements the answer should connect to.
        results = session.retriever.retrieve_balanced(
            f"{asked.question.question} {answer[:600]}", k_per_doc=3, min_score=MIN_CONTEXT_SCORE
        )
        context, used = self._context(dedupe(results + asked.context))
        job_skills = [s.name for s in session.match.matching_skills + session.match.missing_skills]

        evaluation, generated_by, warnings = self._generate(
            lambda llm: generate_structured(
                llm, prompts.GROUNDING_RULES,
                prompts.evaluation_prompt(asked.question.question, asked.question.category,
                                          asked.question.expected_points, answer, context),
                AnswerEvaluation,
            ),
            lambda: self.offline.evaluate(asked.question, answer, used, job_skills),
        )
        asked.scores.append(evaluation.overall_score)
        return EvaluationResponse(
            session_id=session_id, question_id=question_id, score=evaluation.overall_score,
            evaluation=evaluation, sources=[to_source(r) for r in used], generated_by=generated_by, warnings=warnings,
        )

    def _session_with_question(self, session_id: str, question_id: str) -> Session:
        session = self.sessions.get(session_id)
        if question_id not in session.questions:
            raise CoachError("Unknown question for this session. Please generate a new question.")
        return session
