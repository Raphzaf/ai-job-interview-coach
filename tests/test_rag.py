"""Structured output handling, prompts, interview planning and the RAG pipeline."""

import json

import pytest

from app.core.errors import LLMError
from app.core.sessions import SessionStore
from app.models.schemas import AnalyzeRequest, AnswerEvaluation, InterviewQuestion, MatchInsights
from app.rag import prompts
from app.rag.interview_planner import InterviewPlanner
from app.rag.llm import extract_json, generate_structured
from app.rag.pipeline import CoachPipeline
from tests.conftest import VALID_EVALUATION, VALID_INSIGHTS, VALID_QUESTION, FakeLLM


# --- JSON extraction & validation ------------------------------------------------------

def test_extract_json_plain_fenced_and_chatty():
    assert extract_json('{"a": 1}') == {"a": 1}
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Sure! Here it is: {"a": {"b": 2}} Hope it helps') == {"a": {"b": 2}}


@pytest.mark.parametrize("bad", ["no json here", "[1, 2]", '{"a": '])
def test_extract_json_rejects_invalid(bad):
    with pytest.raises(json.JSONDecodeError):
        extract_json(bad)


def test_generate_structured_valid_first_try():
    llm = FakeLLM([VALID_QUESTION])
    q = generate_structured(llm, "sys", "user", InterviewQuestion)
    assert q.category == "technical" and len(llm.calls) == 1


def test_generate_structured_repairs_once_with_error_feedback():
    llm = FakeLLM(['{"question": "too short"}', VALID_QUESTION])
    q = generate_structured(llm, "sys", "user", InterviewQuestion)
    assert q.focus == "Vector Databases"
    repair_message = llm.calls[1][-1]["content"]
    assert "not valid" in repair_message and "category" in repair_message


def test_generate_structured_raises_after_repair_budget():
    llm = FakeLLM(["not json", "still not json"])
    with pytest.raises(LLMError, match="invalid InterviewQuestion"):
        generate_structured(llm, "sys", "user", InterviewQuestion)


def test_schema_validation_rules():
    data = json.loads(VALID_EVALUATION)
    evaluation = AnswerEvaluation.model_validate(data)
    assert evaluation.overall_score == 7.0  # mean of criteria, computed in code
    data["criteria"]["relevance"] = 11
    with pytest.raises(ValueError):
        AnswerEvaluation.model_validate(data)
    insights = MatchInsights.model_validate({**json.loads(VALID_INSIGHTS), "strengths": ["A", "a", " ", "B"]})
    assert insights.strengths == ["A", "B"]  # blanks and case-duplicates removed
    with pytest.raises(ValueError):
        InterviewQuestion.model_validate({**json.loads(VALID_QUESTION), "category": "trivia"})


# --- prompts ------------------------------------------------------------------------------

def test_context_is_numbered_labelled_and_budgeted(retriever, counter):
    results = retriever.retrieve_balanced("Python FAISS AWS", k_per_doc=3)
    text, used = prompts.format_context(results, counter, max_tokens=10_000)
    assert "[S1]" in text and "CV ›" in text or "Job description ›" in text
    assert len(used) == len(results)
    _, small = prompts.format_context(results, counter, max_tokens=50)
    assert 1 <= len(small) < len(results)


def test_prompts_contain_grounding_instructions():
    for rule in ("Never invent candidate experience", "Never invent job requirements", "not available in the documents",
                 "General advice:"):
        assert rule in prompts.GROUNDING_RULES
    assert "placeholder" in prompts.evaluation_prompt("Q?", "technical", ["p"], "answer", "ctx")
    assert "Do NOT change" in prompts.insights_prompt({"overall_score": 50}, "ctx")


# --- planner -------------------------------------------------------------------------------

def _report(sample_docs, retriever):
    from app.matching.matcher import Matcher

    cv, job = sample_docs
    return Matcher().analyze(cv, job, retriever)


def test_planner_rotates_categories_and_varies_focus(sample_docs, retriever):
    planner = InterviewPlanner(_report(sample_docs, retriever))
    plans = [planner.next() for _ in range(8)]
    assert [p.category for p in plans[:4]] == ["technical", "experience", "gap", "behavioral"]
    technical_focus = [p.focus for p in plans if p.category == "technical"]
    assert len(set(technical_focus)) == len(technical_focus)
    gap = next(p for p in plans if p.category == "gap")
    assert gap.focus == "AWS"  # the only missing required skill


def test_planner_honours_requested_category(sample_docs, retriever):
    planner = InterviewPlanner(_report(sample_docs, retriever))
    assert planner.next("behavioral").category == "behavioral"


# --- pipeline ---------------------------------------------------------------------------------

def _pipeline(settings, processor, embedder, llm):
    return CoachPipeline(settings, processor, embedder, llm, SessionStore())


def _analyze(pipeline, sample_cv_text, sample_job_text):
    return pipeline.analyze(AnalyzeRequest(cv_text=sample_cv_text, job_text=sample_job_text))


def test_full_rag_flow_with_llm(settings, processor, embedder, sample_cv_text, sample_job_text):
    llm = FakeLLM([VALID_INSIGHTS, VALID_QUESTION, VALID_EVALUATION])
    pipeline = _pipeline(settings, processor, embedder, llm)

    analysis = _analyze(pipeline, sample_cv_text, sample_job_text)
    assert analysis.insights_generated_by == "llm" and analysis.insights_sources
    # The insights prompt contains the grounding rules, retrieved CV evidence and the computed score.
    system, user = llm.calls[0][0]["content"], llm.calls[0][1]["content"]
    assert "Never invent" in system
    assert "[S1]" in user and "Brightleaf" in user and str(analysis.match.overall_score) in user

    question = pipeline.next_question(analysis.session_id)
    assert question.generated_by == "llm" and question.sources
    assert question.question.category == "technical"  # set by the planner

    feedback = pipeline.evaluate(analysis.session_id, question.question_id, "I used a flat FAISS index.")
    assert feedback.score == 7.0 and feedback.generated_by == "llm"
    assert "I used a flat FAISS index." in llm.calls[2][1]["content"]


def test_planner_category_overrides_llm_category(settings, processor, embedder, sample_cv_text, sample_job_text):
    wrong = json.dumps({**json.loads(VALID_QUESTION), "category": "behavioral"})
    pipeline = _pipeline(settings, processor, embedder, FakeLLM([VALID_INSIGHTS, wrong]))
    sid = _analyze(pipeline, sample_cv_text, sample_job_text).session_id
    assert pipeline.next_question(sid, "gap").question.category == "gap"


def test_llm_failure_falls_back_to_offline(settings, processor, embedder, sample_cv_text, sample_job_text):
    llm = FakeLLM([LLMError("Service down."), "garbage", "garbage"])
    pipeline = _pipeline(settings, processor, embedder, llm)
    analysis = _analyze(pipeline, sample_cv_text, sample_job_text)
    assert analysis.insights_generated_by == "offline-fallback"
    assert "Service down." in analysis.warnings[0]
    q = pipeline.next_question(analysis.session_id)  # invalid JSON twice -> fallback
    assert q.generated_by == "offline-fallback" and q.question.question


def test_llm_failure_raises_when_fallback_disabled(settings, processor, embedder, sample_cv_text, sample_job_text):
    strict = settings.model_copy(update={"llm_fallback_to_offline": False})
    pipeline = _pipeline(strict, processor, embedder, FakeLLM([LLMError("Service down.")]))
    with pytest.raises(LLMError):
        _analyze(pipeline, sample_cv_text, sample_job_text)


def test_offline_mode_end_to_end(settings, processor, embedder, sample_cv_text, sample_job_text):
    pipeline = _pipeline(settings, processor, embedder, None)
    analysis = _analyze(pipeline, sample_cv_text, sample_job_text)
    assert analysis.insights_generated_by == "offline"
    categories = []
    for _ in range(4):
        q = pipeline.next_question(analysis.session_id)
        categories.append(q.question.category)
        assert q.generated_by == "offline"
    assert set(categories) == {"technical", "experience", "gap", "behavioral"}


def test_offline_evaluation_ranks_good_answer_above_weak(settings, processor, embedder, sample_cv_text, sample_job_text):
    pipeline = _pipeline(settings, processor, embedder, None)
    sid = _analyze(pipeline, sample_cv_text, sample_job_text).session_id
    q = pipeline.next_question(sid, "behavioral")
    good = ("When I was at Brightleaf, our goal was to reduce support ticket handling time. I organised weekly "
            "sessions with the product manager and support leads, I designed the RAG assistant with FAISS and "
            "FastAPI, and as a result handling time decreased by 18%.")
    weak = "I am a team player."
    good_score = pipeline.evaluate(sid, q.question_id, good).score
    weak_score = pipeline.evaluate(sid, q.question_id, weak).score
    assert good_score > weak_score + 3
