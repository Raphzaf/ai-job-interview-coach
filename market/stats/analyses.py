"""Statistical analyses of the job-market data (SciPy + statsmodels).

Each function answers one research question and returns a plain dict with
the hypotheses, the test, its assumptions check, statistic, p-value, effect
size and an interpretation threshold. Functions are pure (DataFrame in,
dict out) so they can be unit-tested on synthetic data.

Two principles:
- With hundreds of thousands of rows almost any difference is "significant",
  so every test reports an EFFECT SIZE, and interpretation relies on it.
- Observational data: results are associations, never causal effects.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats
from statsmodels.stats.contingency_tables import StratifiedTable
from statsmodels.stats.diagnostic import het_breuschpagan
from statsmodels.stats.multitest import multipletests
from statsmodels.stats.outliers_influence import variance_inflation_factor

SENIOR_ROLES = ["Data Analyst", "Data Engineer", "Data Scientist"]  # roles with a "Senior" variant
EXPERIENCE_ORDER = ["student_intern", "entry", "mid", "experienced", "lead_manager"]


# --- effect-size helpers -------------------------------------------------------------------

def cliffs_delta_label(d: float) -> str:
    """Romano et al. (2006) thresholds for Cliff's delta / rank-biserial correlation."""
    a = abs(d)
    return "negligible" if a < 0.147 else "small" if a < 0.33 else "medium" if a < 0.474 else "large"


def cramers_v(chi2: float, n: int, shape: tuple[int, int]) -> float:
    return float(np.sqrt(chi2 / (n * (min(shape) - 1))))


def cramers_v_label(v: float, df_star: int) -> str:
    """Cohen (1988) thresholds, adjusted for min(r, c) - 1."""
    small, medium, large = (0.1, 0.3, 0.5) if df_star == 1 else (0.07, 0.21, 0.35) if df_star == 2 else (0.06, 0.17, 0.29)
    return "negligible" if v < small else "small" if v < medium else "medium" if v < large else "large"


def describe(series: pd.Series) -> dict:
    s = series.dropna()
    q1, med, q3 = np.percentile(s, [25, 50, 75])
    return {"n": int(len(s)), "mean": round(float(s.mean()), 3), "sd": round(float(s.std(ddof=1)), 3),
            "median": float(med), "q1": float(q1), "q3": float(q3), "min": float(s.min()), "max": float(s.max()),
            "skewness": round(float(stats.skew(s)), 3)}


# --- A. Seniority and number of skills (reference, 2023) ----------------------------------------

def senior_skill_count_test(df: pd.DataFrame, roles: list[str] = SENIOR_ROLES) -> dict:
    """Do senior postings list more skills than non-senior postings of the same role family?

    Stratified by role family (seniority mix differs by role, so a pooled test
    would partly measure role differences). Mann-Whitney U because skill counts
    are discrete and right-skewed; the t-test's normality is not plausible and
    the question is about the distribution, not only the mean.
    """
    data = df[~df["skills_missing"] & df["role_family"].isin(roles)]
    rows = []
    for role in roles:
        g = data[data["role_family"] == role]
        senior = g.loc[g["is_senior"], "skill_count"].to_numpy()
        other = g.loc[~g["is_senior"], "skill_count"].to_numpy()
        u, p = stats.mannwhitneyu(senior, other, alternative="two-sided")
        delta = 2 * u / (len(senior) * len(other)) - 1          # Cliff's delta = rank-biserial r
        diff = senior.mean() - other.mean()
        se = np.sqrt(senior.var(ddof=1) / len(senior) + other.var(ddof=1) / len(other))
        rows.append({
            "role_family": role, "n_senior": len(senior), "n_non_senior": len(other),
            "mean_senior": round(senior.mean(), 3), "mean_non_senior": round(other.mean(), 3),
            "median_senior": float(np.median(senior)), "median_non_senior": float(np.median(other)),
            "skew_senior": round(float(stats.skew(senior)), 2), "skew_non_senior": round(float(stats.skew(other)), 2),
            "mean_difference": round(diff, 3),
            "mean_difference_ci95": [round(diff - 1.96 * se, 3), round(diff + 1.96 * se, 3)],
            "U": float(u), "p_value": float(p),
            "prob_senior_lists_more": round(u / (len(senior) * len(other)), 4),
            "cliffs_delta": round(delta, 4), "effect": cliffs_delta_label(delta),
        })
    holm = multipletests([r["p_value"] for r in rows], method="holm")[1]
    for r, p_adj in zip(rows, holm):
        r["p_holm"] = float(p_adj)
    return {
        "question": "Do senior postings list more skills than non-senior postings of the same role family?",
        "data": "data_jobs 2023, postings with extracted skills, role families with a Senior variant",
        "h0": "Within each role family, the distribution of skill counts is the same for senior and non-senior postings.",
        "h1": "The distributions differ (two-sided).",
        "test": "Mann-Whitney U per role family, Holm correction across the 3 tests",
        "assumptions": "Independent observations; ordinal/continuous outcome. Skill counts are skewed "
                       "(see skewness columns), so a rank test is used instead of a t-test. Mean differences "
                       "with 95% CI (Welch/normal approximation, valid at these sample sizes) are reported for readability.",
        "effect_size": "Cliff's delta (= rank-biserial r): P(senior > non-senior) - P(senior < non-senior); "
                       "|d| < 0.147 negligible, < 0.33 small, < 0.474 medium, else large",
        "results": rows,
    }


# --- B. Remote work and job family (both sources, analysed separately) --------------------------

def remote_association_test(df: pd.DataFrame, group_col: str, remote_col: str, label: str) -> dict:
    table = pd.crosstab(df[group_col], df[remote_col])
    chi2, p, dof, expected = stats.chi2_contingency(table.to_numpy(), correction=False)
    n = int(table.to_numpy().sum())
    v = cramers_v(chi2, n, table.shape)
    low = int((expected < 5).sum())
    residuals = (table.to_numpy() - expected) / np.sqrt(expected)
    remote_idx = list(table.columns).index(True)
    shares = (table[True] / table.sum(axis=1) * 100).round(2)
    return {
        "question": f"Is remote work associated with the {group_col.replace('_', ' ')}? ({label})",
        "h0": f"Remote status is independent of {group_col}.",
        "h1": f"Remote status depends on {group_col}.",
        "test": "Pearson chi-square test of independence",
        "assumptions": f"Independent postings; expected counts >= 5 in at least 80% of cells "
                       f"({low} of {expected.size} cells below 5, smallest {expected.min():.2f}).",
        "assumption_ok": low / expected.size <= 0.2 and expected.min() >= 1,
        "n": n, "chi2": round(float(chi2), 3), "dof": int(dof), "p_value": float(p),
        "cramers_v": round(v, 4), "effect": cramers_v_label(v, min(table.shape) - 1),
        "remote_share_pct": shares.sort_values(ascending=False).to_dict(),
        "standardized_residual_remote": {k: round(float(r), 2) for k, r in zip(table.index, residuals[:, remote_idx])},
    }


# --- C. Skills over-represented in senior postings (stratified by role) -------------------------

def senior_skill_association(df: pd.DataFrame, skill_matrix: pd.DataFrame, roles: list[str] = SENIOR_ROLES,
                             min_postings: int = 5000) -> dict:
    """Which skills are associated with seniority WITHIN role families?

    Cochran-Mantel-Haenszel test over the 2x2 (senior x has-skill) tables of the
    three role families: controls for role mix (e.g. senior engineering roles
    are more frequent than senior analyst roles). Benjamini-Hochberg FDR control
    across all skills tested.
    """
    base = df[~df["skills_missing"] & df["role_family"].isin(roles)][["job_id", "role_family", "is_senior"]]
    matrix = skill_matrix.reindex(base["job_id"]).fillna(False).astype(bool)
    rows = []
    for skill in matrix.columns:
        has = matrix[skill].to_numpy()
        if has.sum() < min_postings:
            continue
        tables = []
        for role in roles:
            mask = (base["role_family"] == role).to_numpy()
            s, h = base["is_senior"].to_numpy()[mask], has[mask]
            tables.append(np.array([[np.sum(s & h), np.sum(s & ~h)], [np.sum(~s & h), np.sum(~s & ~h)]], dtype=float))
        st = StratifiedTable(tables)
        test = st.test_null_odds(correction=True)
        lo, hi = st.oddsratio_pooled_confint()
        rows.append({
            "skill": skill, "postings_with_skill": int(has.sum()),
            "senior_share_pct": round(100 * has[base["is_senior"].to_numpy()].mean(), 2),
            "non_senior_share_pct": round(100 * has[~base["is_senior"].to_numpy()].mean(), 2),
            "mh_odds_ratio": round(float(st.oddsratio_pooled), 3), "or_ci95": [round(float(lo), 3), round(float(hi), 3)],
            "cmh_statistic": round(float(test.statistic), 2), "p_value": float(test.pvalue),
            "homogeneity_p": float(st.test_equal_odds().pvalue),
        })
    reject, q, _, _ = multipletests([r["p_value"] for r in rows], alpha=0.05, method="fdr_bh")
    for r, q_value, rej in zip(rows, q, reject):
        r["q_value_bh"] = float(q_value)
        r["significant_fdr_5pct"] = bool(rej)
    rows.sort(key=lambda r: r["mh_odds_ratio"], reverse=True)
    return {
        "question": "Which skills appear disproportionately often in senior postings, within the same role family?",
        "data": f"data_jobs 2023, {len(base):,} postings with skills in {', '.join(roles)}; skills present in >= {min_postings:,} of them",
        "h0": "For a given skill, the odds of mentioning it are the same for senior and non-senior postings (common OR = 1 across role strata).",
        "h1": "Common odds ratio != 1.",
        "test": "Cochran-Mantel-Haenszel test (stratified by role family) per skill; Benjamini-Hochberg FDR at 5%",
        "assumptions": "Independent postings; large stratum counts (min_postings filter). Breslow-Day homogeneity "
                       "p-value reported: a small value means the association differs between role families, "
                       "so the pooled odds ratio is an average, to be read with the per-role shares.",
        "effect_size": "Mantel-Haenszel pooled odds ratio with 95% CI (OR > 1: more frequent in senior postings)",
        "results": rows,
    }


# --- D. Salary model (statsmodels OLS) --------------------------------------------------------------

def salary_model(df: pd.DataFrame, country: str = "United States", min_role_n: int = 100) -> dict:
    """Which posting characteristics are associated with the advertised salary?

    log(salary) makes the right-skewed salaries roughly symmetric and turns
    coefficients into approximate % differences. One country only, so currency
    and national pay levels are not confounded with role. Heteroscedasticity-
    robust (HC3) standard errors.
    """
    d = df[(df["country"] == country) & df["salary_year_avg"].notna() & ~df["skills_missing"]].copy()
    role_n = d["role_family"].value_counts()
    kept_roles = role_n[role_n >= min_role_n].index
    dropped = {k: int(v) for k, v in role_n[role_n < min_role_n].items()}
    d = d[d["role_family"].isin(kept_roles)].copy()
    d["log_salary"] = np.log(d["salary_year_avg"])
    d["is_senior"] = d["is_senior"].astype(int)
    d["work_from_home"] = d["work_from_home"].astype(int)
    formula = "log_salary ~ C(role_family, Treatment('Data Analyst')) + is_senior + work_from_home + skill_count"
    ols = smf.ols(formula, data=d).fit()
    robust = ols.get_robustcov_results(cov_type="HC3")
    names = ols.model.exog_names
    ci = robust.conf_int()
    coefs = []
    for i, name in enumerate(names):
        if name == "Intercept":
            continue
        b = robust.params[i]
        coefs.append({
            "term": name.replace("C(role_family, Treatment('Data Analyst'))[T.", "role: ").rstrip("]"),
            "coef": round(float(b), 4), "pct_effect": round(100 * (np.exp(b) - 1), 2),
            "ci95_pct": [round(100 * (np.exp(ci[i][0]) - 1), 2), round(100 * (np.exp(ci[i][1]) - 1), 2)],
            "p_value": float(robust.pvalues[i]),
        })
    bp_lm, bp_p, _, _ = het_breuschpagan(ols.resid, ols.model.exog)
    exog = ols.model.exog
    vif = {names[i]: round(float(variance_inflation_factor(exog, i)), 2) for i in range(1, exog.shape[1])}
    return {
        "question": f"Which posting characteristics are associated with the advertised annual salary ({country}, 2023)?",
        "data": f"data_jobs 2023, {country}, postings with an annual salary and extracted skills; n = {len(d):,}"
                + (f"; roles with < {min_role_n} salaries excluded: {dropped}" if dropped else ""),
        "model": formula + "  (OLS, HC3 robust standard errors)",
        "h0": "Each coefficient = 0 (no association with log salary, holding the other terms constant).",
        "h1": "Coefficient != 0.",
        "assumptions": {
            "log_salary_skewness": round(float(stats.skew(d["log_salary"])), 3),
            "residual_skewness": round(float(stats.skew(ols.resid)), 3),
            "residual_excess_kurtosis": round(float(stats.kurtosis(ols.resid)), 3),
            "breusch_pagan_p": float(bp_p),
            "note": "Breusch-Pagan tests constant residual variance; HC3 standard errors are used either way. "
                    "Residual skewness/kurtosis checks approximate normality (inference relies mostly on the "
                    "large n). VIF < 5 indicates no problematic multicollinearity.",
            "vif": vif,
        },
        "n": int(ols.nobs), "r_squared": round(float(ols.rsquared), 4), "adj_r_squared": round(float(ols.rsquared_adj), 4),
        "f_pvalue": float(robust.f_pvalue),
        "coefficients": coefs,
    }


# --- E. Experience level and skills (live snapshot) ---------------------------------------------

def experience_skill_test(df: pd.DataFrame) -> dict:
    """Do postings for more experienced profiles list more skills? (Arbeitnow 2026 snapshot)

    Employer-stated level (ordinal). Kruskal-Wallis across levels + Spearman
    rank correlation with the level order. Repeated within description
    language, because the skill taxonomy is English-oriented and the share of
    English descriptions differs by level (a confounder).
    """
    d = df[df["experience_level"].notna()].copy()
    d["level_rank"] = d["experience_level"].map({lvl: i for i, lvl in enumerate(EXPERIENCE_ORDER)})

    def run(sub: pd.DataFrame, label: str) -> dict:
        groups = [sub.loc[sub["experience_level"] == lvl, "skill_count"].to_numpy() for lvl in EXPERIENCE_ORDER]
        groups = [g for g in groups if len(g) > 0]
        h, p = stats.kruskal(*groups)
        n = len(sub)
        rho, rho_p = stats.spearmanr(sub["level_rank"], sub["skill_count"])
        return {"subset": label, "n": n,
                "medians": {lvl: float(sub.loc[sub["experience_level"] == lvl, "skill_count"].median())
                            for lvl in EXPERIENCE_ORDER if (sub["experience_level"] == lvl).any()},
                "means": {lvl: round(float(sub.loc[sub["experience_level"] == lvl, "skill_count"].mean()), 2)
                          for lvl in EXPERIENCE_ORDER if (sub["experience_level"] == lvl).any()},
                "kruskal_H": round(float(h), 3), "p_value": float(p),
                "epsilon_squared": round(float(h / (n - 1)), 4),
                "spearman_rho": round(float(rho), 4), "spearman_p": float(rho_p)}

    english_share = (d.groupby("experience_level")["description_language"].apply(lambda s: (s == "en").mean() * 100)
                     .reindex(EXPERIENCE_ORDER).round(2).to_dict())
    return {
        "question": "Do postings for more experienced profiles list more skills? (live snapshot, employer-stated level)",
        "data": f"Arbeitnow API snapshot, {len(d):,} postings with an employer-stated experience level",
        "h0": "Skill-count distributions are identical across experience levels.",
        "h1": "At least one level differs (Kruskal-Wallis); monotonic association with level (Spearman).",
        "test": "Kruskal-Wallis H test + Spearman rank correlation; overall and within description language",
        "assumptions": "Independent postings; ordinal outcome, skewed counts (rank tests). Possible confounder: "
                       "share of English descriptions by level (the skill taxonomy detects more skills in English).",
        "effect_size": "epsilon-squared for Kruskal-Wallis (~0.01 small, ~0.08 medium, ~0.26 large); Spearman rho",
        "english_description_share_pct": english_share,
        "results": [run(d, "all languages"), run(d[d["description_language"] == "en"], "English descriptions"),
                    run(d[d["description_language"] == "de"], "German descriptions")],
    }


# --- Descriptive statistics & correlations --------------------------------------------------------

def descriptive_tables(ref: pd.DataFrame, live: pd.DataFrame) -> dict:
    ref_ok = ref[~ref["skills_missing"]]
    return {
        "reference_skill_count": describe(ref_ok["skill_count"]),
        "reference_skill_count_by_role": {r: describe(g["skill_count"]) for r, g in ref_ok.groupby("role_family")},
        "reference_salary_year": describe(ref["salary_year_avg"]),
        "live_skill_count": describe(live["skill_count"]),
        "live_skill_count_by_family": {f: describe(g["skill_count"]) for f, g in live.groupby("job_family")},
        "live_description_words": describe(live["description_words"]),
    }


REFERENCE_CORR_COLUMNS = ["skill_count", "programming_skill_count", "cloud_skill_count", "libraries_skill_count",
                          "databases_skill_count", "analyst_tools_skill_count", "is_senior", "work_from_home",
                          "salary_year_avg"]


def spearman_correlations(df: pd.DataFrame, columns: list[str] = REFERENCE_CORR_COLUMNS) -> pd.DataFrame:
    """Pairwise Spearman correlations (pairwise-complete: salary only where published)."""
    d = df[~df["skills_missing"]][columns].astype(float)
    return d.corr(method="spearman").round(3)
