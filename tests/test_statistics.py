"""Statistical functions on synthetic data with KNOWN effects (no database)."""

import numpy as np
import pandas as pd
import pytest

from market.stats import analyses as A

RNG = np.random.default_rng(42)


def reference_frame(n: int = 6000, senior_shift: float = 0.0, senior_salary_effect: float = 0.15) -> pd.DataFrame:
    roles = RNG.choice(A.SENIOR_ROLES, n)
    senior = RNG.random(n) < 0.3
    skills = RNG.poisson(4 + senior_shift * senior).astype(float)
    salary = np.exp(11 + senior_salary_effect * senior + 0.3 * (roles == "Data Scientist") + RNG.normal(0, 0.25, n))
    return pd.DataFrame({
        "job_id": [f"j{i}" for i in range(n)], "role_family": roles, "is_senior": senior,
        "work_from_home": RNG.random(n) < 0.1, "country": "United States", "skills_missing": False,
        "skill_count": skills, "salary_year_avg": salary,
    })


def test_effect_size_labels_and_cramers_v():
    assert [A.cliffs_delta_label(d) for d in (0.1, -0.2, 0.4, 0.6)] == ["negligible", "small", "medium", "large"]
    assert A.cramers_v(100.0, 1000, (2, 2)) == pytest.approx(np.sqrt(0.1))
    assert A.cramers_v_label(0.05, 1) == "negligible" and A.cramers_v_label(0.35, 1) == "medium"


def test_describe():
    d = A.describe(pd.Series([1, 2, 3, 4, 100, np.nan]))
    assert d["n"] == 5 and d["median"] == 3 and d["skewness"] > 1


def test_senior_skill_count_detects_shift_and_holds_under_null():
    shifted = A.senior_skill_count_test(reference_frame(senior_shift=2.0))
    for r in shifted["results"]:
        assert r["p_holm"] < 1e-6 and r["cliffs_delta"] > 0.2 and r["mean_difference_ci95"][0] > 0
    null = A.senior_skill_count_test(reference_frame(senior_shift=0.0))
    assert all(abs(r["cliffs_delta"]) < 0.1 for r in null["results"])
    assert sum(r["p_holm"] < 0.05 for r in null["results"]) <= 1   # at most a chance rejection


def test_remote_association_independent_vs_dependent():
    n = 4000
    groups = RNG.choice(["a", "b", "c"], n)
    indep = pd.DataFrame({"g": groups, "remote": RNG.random(n) < 0.2})
    dep = pd.DataFrame({"g": groups, "remote": RNG.random(n) < np.where(groups == "a", 0.6, 0.1)})
    r_indep = A.remote_association_test(indep, "g", "remote", "synthetic")
    r_dep = A.remote_association_test(dep, "g", "remote", "synthetic")
    assert r_indep["cramers_v"] < 0.06 and r_dep["cramers_v"] > 0.4 and r_dep["p_value"] < 1e-10
    assert r_dep["remote_share_pct"]["a"] > 50 and r_dep["assumption_ok"]


def test_cmh_recovers_stratified_odds_ratio():
    df = reference_frame(n=9000)
    # Skill "X": odds doubled for seniors in every role; skill "Y": no association.
    base_p = {"Data Analyst": 0.1, "Data Engineer": 0.3, "Data Scientist": 0.2}
    p = df["role_family"].map(base_p).to_numpy()
    odds = p / (1 - p) * np.where(df["is_senior"], 2.0, 1.0)
    x = RNG.random(len(df)) < odds / (1 + odds)
    y = RNG.random(len(df)) < p
    matrix = pd.DataFrame({"X": x, "Y": y}, index=df["job_id"])
    res = {r["skill"]: r for r in A.senior_skill_association(df, matrix, min_postings=100)["results"]}
    assert res["X"]["or_ci95"][0] < 2.0 < res["X"]["or_ci95"][1] and res["X"]["significant_fdr_5pct"]
    assert res["Y"]["or_ci95"][0] < 1.0 < res["Y"]["or_ci95"][1]


def test_salary_model_recovers_planted_effect():
    df = reference_frame(n=5000, senior_salary_effect=0.15)
    res = A.salary_model(df, min_role_n=10)
    senior = next(c for c in res["coefficients"] if c["term"] == "is_senior")
    expected = 100 * (np.exp(0.15) - 1)                       # 16.18 %
    assert senior["ci95_pct"][0] < expected < senior["ci95_pct"][1]
    ds = next(c for c in res["coefficients"] if "Data Scientist" in c["term"])
    assert ds["ci95_pct"][0] < 100 * (np.exp(0.3) - 1) < ds["ci95_pct"][1]
    assert set(res["assumptions"]) >= {"breusch_pagan_p", "vif", "residual_skewness"}


def test_salary_model_excludes_small_roles():
    df = reference_frame(n=3000)
    df.loc[:4, "role_family"] = "Cloud Engineer"
    res = A.salary_model(df, min_role_n=100)
    assert "Cloud Engineer" in res["data"] and not any("Cloud" in c["term"] for c in res["coefficients"])


def test_experience_test_finds_monotonic_trend_and_stratifies_by_language():
    rows = []
    for rank, level in enumerate(A.EXPERIENCE_ORDER):
        for lang in ("en", "de"):
            rows += [{"experience_level": level, "description_language": lang,
                      "skill_count": float(c)} for c in RNG.poisson(2 + rank, 60)]
    res = A.experience_skill_test(pd.DataFrame(rows))
    subsets = {r["subset"]: r for r in res["results"]}
    assert set(subsets) == {"all languages", "English descriptions", "German descriptions"}
    assert subsets["all languages"]["spearman_rho"] > 0.4 and subsets["all languages"]["p_value"] < 1e-10
