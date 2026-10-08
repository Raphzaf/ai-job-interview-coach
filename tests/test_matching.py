"""Skill normalisation, feature extraction and score calculations."""

from datetime import date
from pathlib import Path

import pytest

from app.matching.matcher import DEFAULT_WEIGHTS, Matcher, compare_skills, rescale
from app.matching.requirements import Requirement, candidate_years, extract_requirements, required_years
from app.matching.skills import alternative_groups, expand_implied, extract_skills, normalize_skill
from app.retrieval.retriever import Retriever

EVAL = Path(__file__).resolve().parents[1] / "evaluation" / "data"


# --- skills ---------------------------------------------------------------------

@pytest.mark.parametrize("alias, canonical", [
    ("postgres", "PostgreSQL"), ("sklearn", "scikit-learn"), ("K8S", "Kubernetes"),
    ("Hugging Face", "Transformers"), ("golang", "Go"), ("unknown skill", None),
])
def test_normalize_skill(alias, canonical):
    assert normalize_skill(alias) == canonical


def test_extract_skills_handles_symbols_and_aliases():
    text = "Python, C++, C# and Node.js. Postgres + sklearn on k8s. Built REST APIs."
    assert set(extract_skills(text)) >= {"Python", "C++", "C#", "Node.js", "PostgreSQL", "scikit-learn", "Kubernetes", "REST APIs"}


def test_extract_skills_avoids_common_false_positives():
    skills = extract_skills("Worked in R&D with the rest of the team, ready to go.")
    assert "R" not in skills and "REST APIs" not in skills and "Go" not in skills


def test_extract_skills_is_stable():
    text = "Docker, Python, AWS"
    assert extract_skills(text) == extract_skills(text) == ["Python", "AWS", "Docker"]


def test_alternative_groups():
    assert alternative_groups("Experience with PyTorch or TensorFlow") == [{"PyTorch", "TensorFlow"}]
    assert alternative_groups("FastAPI/Flask and Docker") == [{"FastAPI", "Flask"}]
    assert alternative_groups("Python and Docker") == []


def test_expand_implied_is_transitive():
    assert {"Generative AI", "LLMs", "Machine Learning"} <= expand_implied(["RAG", "PyTorch"])


def test_compare_skills_respects_alternatives_and_preferred():
    reqs = [Requirement("Python with PyTorch or TensorFlow", "required"), Requirement("Kubernetes", "preferred")]
    skills = compare_skills("Python and PyTorch", "Python with PyTorch or TensorFlow. Kubernetes is a plus.", reqs)
    assert "TensorFlow" not in skills.missing_required
    assert skills.missing_preferred == ["Kubernetes"]
    assert set(skills.matched_required) == {"Python", "PyTorch"}


# --- requirements & experience --------------------------------------------------------

def test_extract_requirements_from_sections(sample_job_text):
    reqs = extract_requirements(sample_job_text)
    assert any("3+ years" in r.text and r.kind == "required" for r in reqs)
    assert any("Kubernetes" in r.text and r.kind == "preferred" for r in reqs)
    assert not any("learning budget" in r.text for r in reqs)  # "What we offer" is not a requirement


def test_extract_requirements_fallback_for_prose():
    reqs = extract_requirements("We need someone who knows Python very well. Docker experience is a plus.")
    assert [r.kind for r in reqs] == ["required", "preferred"]


def test_required_years():
    assert required_years("3+ years of professional experience; 5 years experience with Python") == 5
    assert required_years("No experience required") is None


def test_candidate_years_merges_overlaps_and_ignores_education():
    cv = ("EXPERIENCE\nEngineer\nJan 2020 - Dec 2021\nConsultant (part time)\nJun 2021 - Dec 2022\n\n"
          "EDUCATION\nMSc\n2015 - 2019")
    assert candidate_years(cv, today=date(2026, 1, 1)) == 3.0
    assert candidate_years("EXPERIENCE\nEngineer\nMar 2024 - Present", today=date(2026, 3, 1)) == pytest.approx(2.1)
    assert candidate_years("SKILLS\nPython") is None


# --- score calculations -----------------------------------------------------------------

def test_rescale_clips():
    assert rescale(0.1, 0.2, 0.8) == 0.0 and rescale(0.9, 0.2, 0.8) == 1.0
    assert rescale(0.5, 0.2, 0.8) == pytest.approx(0.5)


def test_combine_renormalises_missing_signals():
    matcher = Matcher()
    overall, weights = matcher.combine(
        {"skill_overlap": 1.0, "requirement_coverage": 0.5, "semantic_similarity": 0.0, "experience": None}
    )
    assert weights["experience"] == 0.0
    assert sum(weights.values()) == pytest.approx(1.0)
    expected = (0.40 * 1.0 + 0.35 * 0.5) / 0.90
    assert overall == pytest.approx(expected)


def test_invalid_weights_rejected():
    with pytest.raises(ValueError):
        Matcher({"skill_overlap": -1})
    with pytest.raises(ValueError):
        Matcher({"magic": 1})
    with pytest.raises(ValueError):
        Matcher({k: 0 for k in DEFAULT_WEIGHTS})


def test_skill_overlap_weights_preferred_half(sample_job_text):
    from app.models.domain import SkillMatch

    skills = SkillMatch(required=["A", "B"], preferred=["C", "D"], matched_required=["A", "B"], matched_preferred=[])
    assert Matcher.skill_overlap_score(skills) == pytest.approx(2 / 3)
    assert Matcher.skill_overlap_score(SkillMatch()) is None


def test_experience_score():
    assert Matcher.experience_score(4, 2.0) == 0.5
    assert Matcher.experience_score(4, 6.0) == 1.0
    assert Matcher.experience_score(None, 6.0) is None


def test_analyze_report_is_consistent(sample_docs, retriever):
    cv, job = sample_docs
    report = Matcher().analyze(cv, job, retriever)
    assert 0 <= report.overall_score <= 100
    applicable = [c for c in report.breakdown if c.applicable]
    assert sum(c.weight for c in report.breakdown) == pytest.approx(1.0, abs=1e-3)
    assert report.overall_score == pytest.approx(sum(c.score * c.weight for c in applicable), abs=0.2)
    assert "AWS" in {s.name for s in report.missing_skills}
    assert "Python" in {s.name for s in report.matching_skills}
    assert report.disclaimer


def test_analyze_is_deterministic(sample_docs, retriever):
    cv, job = sample_docs
    assert Matcher().analyze(cv, job, retriever) == Matcher().analyze(cv, job, retriever)


def test_matching_pair_scores_higher_than_mismatched_pair(processor, embedder):
    def score(cv_file, job_file):
        cv = processor.prepare((EVAL / cv_file).read_text(), "cv", cv_file)
        job = processor.prepare((EVAL / job_file).read_text(), "job", job_file)
        r = Retriever.from_chunks(embedder, processor.chunk(cv) + processor.chunk(job))
        return Matcher().analyze(cv, job, r).overall_score

    assert score("cv_ml_engineer.txt", "job_ml_engineer.txt") > score("cv_marketing_coordinator.txt", "job_ml_engineer.txt") + 20
    assert score("cv_marketing_coordinator.txt", "job_marketing_manager.txt") > score("cv_ml_engineer.txt", "job_marketing_manager.txt")
