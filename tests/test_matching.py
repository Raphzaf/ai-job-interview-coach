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


# --- out-of-domain jobs (final audit: ML CV scored 58.8% against a nurse job) ------------

NURSE_JOB = ("Registered Nurse - Intensive Care Unit\nCity Hospital\n\nRequirements\n- State nursing licence\n"
             "- 3+ years of ICU experience\n- Patient assessment and medication administration\n"
             "- Calm communication with families\n")
CHEF_JOB = ("Head Chef\nBistro Lumiere\n\nRequirements\n- 5+ years running a professional kitchen\n"
            "- Menu design and food cost control\n- Leadership of a team of 8 cooks\n- Strong communication skills\n")
FEW_SKILLS_JOB = "Data Engineer\nAcme\n\nRequirements\n- Strong Python\n- 3+ years building data pipelines\n"
INCOMPLETE_JOB = "Data Engineer at Acme. We need someone good with data pipelines and Python. Apply now!"


@pytest.fixture
def analyze(processor, embedder, sample_cv_text):
    def run(job_text, cv_text=None):
        cv = processor.prepare(cv_text or sample_cv_text, "cv", "cv.txt")
        job = processor.prepare(job_text, "job", "job.txt")
        retriever = Retriever.from_chunks(embedder, processor.chunk(cv) + processor.chunk(job))
        report = Matcher().analyze(cv, job, retriever)
        return report, {c.key: c for c in report.breakdown}
    return run


def test_soft_skills_count_half_in_the_skill_signal():
    from app.models.domain import SkillMatch

    skills = SkillMatch(required=["Python", "Communication"], matched_required=["Communication"])
    assert Matcher.skill_overlap_score(skills) == pytest.approx(0.5 / 1.5)
    # Spoken languages are concrete requirements and keep their full weight.
    assert Matcher.skill_weight("English") == 1.0 and Matcher.skill_weight("Leadership") == 0.5


def test_skill_signal_weight_shrinks_when_the_job_lists_few_skills():
    from app.models.domain import SkillMatch

    assert Matcher.skill_reliability(SkillMatch(required=["Communication"])) == pytest.approx(0.5 / 3)
    assert Matcher.skill_reliability(SkillMatch(required=["Python"])) == pytest.approx(1 / 3)
    assert Matcher.skill_reliability(SkillMatch(required=["Python", "SQL", "Docker"])) == 1.0
    overall, weights = Matcher().combine(
        {"skill_overlap": 1.0, "requirement_coverage": 0.2, "semantic_similarity": 0.0, "experience": None},
        {"skill_overlap": 1 / 3},
    )
    assert weights["skill_overlap"] == pytest.approx(0.40 / 3 / (0.40 / 3 + 0.35 + 0.15))
    assert sum(weights.values()) == pytest.approx(1.0)


def test_experience_is_credited_in_proportion_to_requirement_coverage():
    assert Matcher.experience_score(3, 6.0, coverage=0.9) == 1.0   # relevant CV: no penalty
    assert Matcher.experience_score(3, 6.0, coverage=0.35) == pytest.approx(0.5)
    assert Matcher.experience_score(3, 6.0, coverage=None) == 1.0  # nothing to judge relevance against


def test_relevant_cv_keeps_full_weights_and_a_high_score(analyze, sample_job_text):
    report, parts = analyze(sample_job_text)
    assert parts["skill_overlap"].weight == pytest.approx(DEFAULT_WEIGHTS["skill_overlap"])
    assert parts["experience"].score == 100.0
    assert "reduced" not in parts["skill_overlap"].explanation


def test_ml_cv_vs_nurse_job_is_not_inflated_by_one_soft_skill(analyze, sample_job_text):
    relevant, _ = analyze(sample_job_text)
    report, parts = analyze(NURSE_JOB)
    assert [s.name for s in report.matching_skills] == ["Communication"]
    assert parts["skill_overlap"].weight < 0.15 and "reduced" in parts["skill_overlap"].explanation
    assert parts["experience"].score < 50 and "Credited at" in parts["experience"].explanation
    assert report.overall_score < relevant.overall_score - 40


def test_jobs_sharing_only_soft_skills_are_not_covered_by_them(analyze):
    report, parts = analyze(CHEF_JOB)
    by_text = {c.text: c for c in report.requirements}
    leadership = by_text["Leadership of a team of 8 cooks"]
    assert leadership.matched_skills == ["Leadership"] and leadership.status != "covered"
    assert parts["skill_overlap"].weight < DEFAULT_WEIGHTS["skill_overlap"]


def test_job_with_very_few_skills_still_scores_a_relevant_cv(analyze):
    report, parts = analyze(FEW_SKILLS_JOB)
    assert parts["skill_overlap"].score == 100.0 and parts["skill_overlap"].weight < DEFAULT_WEIGHTS["skill_overlap"]
    assert 0 <= report.overall_score <= 100


def test_incomplete_job_ad_degrades_gracefully(analyze):
    report, parts = analyze(INCOMPLETE_JOB)
    assert not parts["experience"].applicable  # no "N+ years" stated
    assert sum(c.weight for c in report.breakdown) == pytest.approx(1.0, abs=0.01)
    assert 0 <= report.overall_score <= 100
