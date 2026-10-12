"""Market context: the bridge between the data-analytics layer and the coach."""

from __future__ import annotations

import json

import pytest

from app.core.sessions import SessionStore
from app.market_context import MarketContextService, detect_role_family
from app.market_context.service import DEFAULT_FILE
from app.matching.skills import SKILL_TAXONOMY
from app.models.schemas import AnalyzeRequest
from app.rag.pipeline import CoachPipeline
from market.coach_context import build_context
from tests.conftest import EVAL_DATA, VALID_INSIGHTS, FakeLLM, make_client


@pytest.fixture(scope="module")
def service() -> MarketContextService:
    svc = MarketContextService.load()
    assert svc is not None
    return svc


def test_shipped_file_is_reproducible_from_the_validated_extract():
    # The JSON shipped with the app must be exactly what the builder produces
    # from the dashboard extract (itself validated against PostgreSQL).
    assert json.loads(DEFAULT_FILE.read_text(encoding="utf-8")) == build_context()


def test_numbers_match_the_dashboard(service):
    de = service.data["roles"]["Data Engineer"]
    # Same figures as docs/DASHBOARD.md (SQL 67.5 %, Python 64.9 %, AWS 38.6 %).
    assert round(100 * de["skills"]["SQL"] / de["postings"], 1) == 67.5
    assert round(100 * de["skills"]["AWS"] / de["postings"], 1) == 38.6
    assert service.data["total_postings"] == 667_989
    assert sum(r["postings"] for r in service.data["roles"].values()) == 667_989


def test_skill_names_use_the_coach_taxonomy(service):
    for role in service.data["roles"].values():
        assert set(role["skills"]) <= set(SKILL_TAXONOMY)


@pytest.mark.parametrize(("title", "role"), [
    ("Machine Learning Engineer - NLP & Generative AI", "Machine Learning Engineer"),
    ("Senior Data Engineer (Spark, AWS)", "Data Engineer"),
    ("Junior Data Analyst", "Data Analyst"),
    ("Data Scientist, Pricing", "Data Scientist"),
    ("Senior Python Backend Developer", "Software Engineer"),
    ("DevOps Engineer", "Cloud Engineer"),
    ("Digital Marketing Specialist", None),
    ("Office Manager", None),
])
def test_role_detection_from_title(title, role):
    assert detect_role_family(title) == role


def test_analysis_shows_market_demand_for_missing_skills(settings, sample_cv_text, sample_job_text):
    with make_client(settings) as client:
        r = client.post("/api/analyze", json={"cv_text": sample_cv_text, "job_text": sample_job_text}).json()
    market = r["market"]
    assert market["available"] and market["role_family"] == "Machine Learning Engineer"
    missing = {d["skill"]: d for d in market["missing_skill_demand"]}
    assert "AWS" in missing and not missing["AWS"]["in_cv"] and missing["AWS"]["in_job"]
    assert 0 < missing["AWS"]["share"] < 100
    shares = [d["share"] for d in market["top_skills"]]
    assert shares == sorted(shares, reverse=True) and len(shares) == 10
    # Informational only: identical score with the market context disabled.
    with make_client(settings.model_copy(update={"market_context_enabled": False})) as client:
        r2 = client.post("/api/analyze", json={"cv_text": sample_cv_text, "job_text": sample_job_text}).json()
    assert r2["market"] is None and r2["match"]["overall_score"] == r["match"]["overall_score"]


def test_no_market_figures_for_jobs_outside_the_dataset(settings):
    cv = (EVAL_DATA / "cv_marketing_coordinator.txt").read_text(encoding="utf-8")
    job = (EVAL_DATA / "job_marketing_manager.txt").read_text(encoding="utf-8")
    with make_client(settings) as client:
        market = client.post("/api/analyze", json={"cv_text": cv, "job_text": job}).json()["market"]
    assert not market["available"] and market["role_family"] is None
    assert market["missing_skill_demand"] == [] and market["top_skills"] == []


def test_missing_file_disables_the_context(tmp_path):
    assert MarketContextService.load(tmp_path / "absent.json") is None


def test_market_demand_reaches_the_llm_prompt(settings, processor, embedder, service, sample_cv_text, sample_job_text):
    llm = FakeLLM([VALID_INSIGHTS])
    pipeline = CoachPipeline(settings, processor, embedder, llm, SessionStore(), market=service)
    pipeline.analyze(AnalyzeRequest(cv_text=sample_cv_text, job_text=sample_job_text))
    prompt = llm.calls[0][1]["content"]
    assert "job_market_demand_for_missing_skills" in prompt and "lukebarousse/data_jobs" in prompt
