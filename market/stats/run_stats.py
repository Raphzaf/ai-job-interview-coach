"""Run the full statistical analysis and save results + figures.

    python -m market.stats.run_stats        # reads PostgreSQL via DATABASE_URL (read-only role)

Outputs
- data/processed/stats_results/*.json    one file per research question (all numbers)
- data/processed/stats_results/*.csv     table view of every figure
- reports/figures/stats/*.png            figures (generated from the data, never drawn by hand)
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from statsmodels.stats.proportion import proportion_confint  # noqa: E402

from market import PROCESSED_DIR, PROJECT_ROOT  # noqa: E402
from market.stats import analyses as A  # noqa: E402
from market.stats.data import live_jobs, query_df, reference_jobs, reference_skill_matrix  # noqa: E402

RESULTS_DIR = PROCESSED_DIR / "stats_results"
FIG_DIR = PROJECT_ROOT / "reports" / "figures" / "stats"

# Reference palette (dataviz skill), light mode; blue/orange pair validated
# with scripts/validate_palette.js (CVD ΔE 24.7, all checks pass).
SURFACE, INK, INK_2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
BLUE, ORANGE = "#2a78d6", "#eb6834"
DIVERGING = ["#184f95", "#3987e5", "#9ec5f4", "#f0efec", "#f2b0ae", "#e34948", "#a32a29"]


def style() -> None:
    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "font.family": "sans-serif", "font.size": 11, "text.color": INK, "axes.labelcolor": INK_2,
        "axes.titlesize": 13, "axes.titleweight": "semibold", "axes.titlecolor": INK, "axes.titlelocation": "left",
        "axes.edgecolor": AXIS, "axes.linewidth": 0.8, "axes.spines.top": False, "axes.spines.right": False,
        "xtick.color": MUTED, "ytick.color": MUTED, "xtick.labelcolor": INK_2, "ytick.labelcolor": INK_2,
        "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True,
        "legend.frameon": False, "legend.labelcolor": INK_2,
    })


def save(fig, name: str, note: str) -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    # Below the axes (negative figure coordinate); bbox_inches="tight" keeps it in the image.
    fig.text(0.01, -0.03, note, fontsize=8.5, color=MUTED, ha="left", va="top")
    fig.savefig(FIG_DIR / f"{name}.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def write_json(name: str, payload) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / f"{name}.json").write_text(json.dumps(payload, indent=2, default=_jsonable), encoding="utf-8")


def _jsonable(v):
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    if isinstance(v, np.bool_):
        return bool(v)
    raise TypeError(type(v))


# --- figures --------------------------------------------------------------------------------------

def fig_skill_count_by_seniority(ref: pd.DataFrame, result: dict) -> None:
    d = ref[~ref["skills_missing"] & ref["role_family"].isin(A.SENIOR_ROLES)]
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.2), sharey=True)
    rows = []
    for ax, role, res in zip(axes, A.SENIOR_ROLES, result["results"]):
        g = d[d["role_family"] == role]
        for senior, color, label in [(False, BLUE, "Non-senior"), (True, ORANGE, "Senior")]:
            counts = g.loc[g["is_senior"] == senior, "skill_count"].clip(upper=15).value_counts(normalize=True).sort_index()
            ax.plot(counts.index, counts.values * 100, color=color, lw=2, marker="o", ms=4, label=label)
            rows += [{"role_family": role, "seniority": label, "skill_count": int(k), "share_pct": round(v * 100, 3)}
                     for k, v in counts.items()]
        ax.set_title(role)
        ax.set_xlabel("Skills listed (15 = 15 or more)")
        ax.text(0.98, 0.95, f"Cliff's δ = {res['cliffs_delta']:.2f} ({res['effect']})", transform=ax.transAxes,
                ha="right", va="top", fontsize=9.5, color=INK_2)
    axes[0].set_ylabel("Share of postings (%)")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper right", ncol=2, bbox_to_anchor=(1.0, 1.04))
    fig.suptitle("Senior postings list slightly more skills, but the effect is small", x=0.01, ha="left",
                 fontsize=14, fontweight="semibold", color=INK, y=1.02)
    pd.DataFrame(rows).to_csv(RESULTS_DIR / "fig_skill_count_by_seniority.csv", index=False)
    save(fig, "A_skill_count_by_seniority",
         "Source: lukebarousse/data_jobs 2023 (Apache-2.0), postings with extracted skills. Mann-Whitney U per role.")


def fig_remote_share(df: pd.DataFrame, group_col: str, remote_col: str, title: str, name: str, source: str) -> None:
    g = df.groupby(group_col)[remote_col].agg(["sum", "count"])
    lo, hi = proportion_confint(g["sum"], g["count"], method="wilson")
    g = g.assign(share=g["sum"] / g["count"] * 100, lo=lo * 100, hi=hi * 100).sort_values("share")
    fig, ax = plt.subplots(figsize=(9, 0.42 * len(g) + 1.4))
    ax.barh(g.index, g["share"], color=BLUE, height=0.62)
    ax.errorbar(g["share"], g.index, xerr=[g["share"] - g["lo"], g["hi"] - g["share"]], fmt="none",
                ecolor=INK_2, elinewidth=1, capsize=3)
    for y, (share, n) in enumerate(zip(g["share"], g["count"])):
        ax.text(g["hi"].iloc[y] + 0.4, y, f"{share:.1f}%  (n={n:,})", va="center", fontsize=9, color=INK_2)
    ax.set_xlabel("Remote postings (%), 95% Wilson CI")
    ax.grid(axis="y", visible=False)
    ax.set_xlim(0, g["hi"].max() * 1.35)
    ax.set_title(title)
    g.round(3).to_csv(RESULTS_DIR / f"fig_{name}.csv")
    save(fig, name, source)


def fig_senior_odds_ratios(result: dict, top: int = 10, bottom: int = 5) -> None:
    rows = result["results"][:top] + result["results"][-bottom:]
    df = pd.DataFrame(rows)[::-1].reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(9, 0.38 * len(df) + 1.5))
    lo = df["mh_odds_ratio"] - df["or_ci95"].map(lambda c: c[0])
    hi = df["or_ci95"].map(lambda c: c[1]) - df["mh_odds_ratio"]
    colors = [ORANGE if o > 1 else BLUE for o in df["mh_odds_ratio"]]
    ax.axvline(1, color=AXIS, lw=1)
    ax.errorbar(df["mh_odds_ratio"], df.index, xerr=[lo, hi], fmt="none", ecolor=INK_2, elinewidth=1, capsize=2)
    ax.scatter(df["mh_odds_ratio"], df.index, c=colors, s=46, zorder=3, edgecolors=SURFACE, linewidths=1.5)
    ax.set_yticks(df.index, df["skill"])
    ax.set_xscale("log")
    ax.set_xticks([0.7, 0.8, 1, 1.25, 1.5, 2], ["0.7", "0.8", "1", "1.25", "1.5", "2"])
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("Mantel-Haenszel odds ratio, senior vs non-senior (log scale, 95% CI)")
    ax.set_ylim(-0.7, len(df) + 0.3)
    ax.text(1.02, len(df) - 0.35, "more frequent in senior postings →", color=INK_2, fontsize=9, va="center")
    ax.text(0.98, len(df) - 0.35, "← less frequent", color=INK_2, fontsize=9, ha="right", va="center")
    ax.set_title("Skills associated with seniority within the same role family", pad=12)
    df.drop(columns=["or_ci95"]).assign(or_low=df["or_ci95"].map(lambda c: c[0]), or_high=df["or_ci95"].map(lambda c: c[1])) \
        .to_csv(RESULTS_DIR / "fig_senior_odds_ratios.csv", index=False)
    save(fig, "C_senior_skill_odds_ratios",
         "Source: data_jobs 2023, Data Analyst/Engineer/Scientist postings with skills. CMH test stratified by role; "
         "all shown skills significant at 5% FDR (Benjamini-Hochberg).")


def fig_salary_coefficients(result: dict) -> None:
    df = pd.DataFrame(result["coefficients"])
    df = df[df["term"] != "skill_count"].copy()  # per-skill effect is on a different scale: reported in the table
    df["label"] = df["term"].str.replace("role: ", "Role: ").replace(
        {"is_senior": "Senior posting", "work_from_home": "Remote (work from home)"}) \
        .str.replace(r"^Role: (.*)$", r"\1 (vs Data Analyst)", regex=True)
    df = df.sort_values("pct_effect").reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(9, 0.5 * len(df) + 1.5))
    lo = df["pct_effect"] - df["ci95_pct"].map(lambda c: c[0])
    hi = df["ci95_pct"].map(lambda c: c[1]) - df["pct_effect"]
    ax.axvline(0, color=AXIS, lw=1)
    ax.errorbar(df["pct_effect"], df.index, xerr=[lo, hi], fmt="none", ecolor=INK_2, elinewidth=1, capsize=3)
    ax.scatter(df["pct_effect"], df.index, color=BLUE, s=50, zorder=3, edgecolors=SURFACE, linewidths=1.5)
    for y, (v, c) in enumerate(zip(df["pct_effect"], df["ci95_pct"])):
        ax.text(c[1] + 1.5, y, f"{v:+.1f}%", va="center", fontsize=9, color=INK_2)
    ax.set_yticks(df.index, df["label"])
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("Difference in advertised salary, holding other terms constant (%, 95% CI, HC3)")
    ax.set_title(f"Salary model (US, 2023): R² = {result['r_squared']:.2f}, n = {result['n']:,}")
    df.to_csv(RESULTS_DIR / "fig_salary_coefficients.csv", index=False)
    save(fig, "D_salary_model",
         "Source: data_jobs 2023, US postings publishing an annual salary. OLS on log(salary); associations, not causal effects.")


def fig_experience_skills(live: pd.DataFrame) -> None:
    d = live[live["experience_level"].notna() & live["description_language"].isin(["en", "de"])]
    means = d.groupby(["experience_level", "description_language"])["skill_count"].agg(["mean", "count"]).reset_index()
    labels = {"student_intern": "Student /\nintern", "entry": "Entry", "mid": "Mid", "experienced": "Experienced",
              "lead_manager": "Lead /\nmanager"}
    x = np.arange(len(A.EXPERIENCE_ORDER))
    fig, ax = plt.subplots(figsize=(9, 4.2))
    for offset, lang, color, label in [(-0.18, "en", BLUE, "English description"), (0.18, "de", ORANGE, "German description")]:
        m = means[means["description_language"] == lang].set_index("experience_level").reindex(A.EXPERIENCE_ORDER)
        ax.bar(x + offset, m["mean"], width=0.34, color=color, label=label)
        for xi, (v, n) in enumerate(zip(m["mean"], m["count"])):
            ax.text(xi + offset, v + 0.12, f"n={int(n)}", ha="center", fontsize=8, color=MUTED)
    ax.set_ylim(0, means["mean"].max() * 1.18)  # headroom for the n= labels
    ax.set_xticks(x, [labels[k] for k in A.EXPERIENCE_ORDER])
    ax.grid(axis="x", visible=False)
    ax.set_ylabel("Mean skills detected per posting")
    ax.legend(loc="upper left")
    ax.set_title("Live snapshot: experience level vs skills, split by description language")
    means.round(3).to_csv(RESULTS_DIR / "fig_experience_skills.csv", index=False)
    save(fig, "E_experience_level_skills",
         "Source: Arbeitnow API snapshot 2026-10-08, postings with an employer-stated level. "
         "The skill taxonomy is English-oriented: compare levels within a language, not across.")


def fig_correlations(corr: pd.DataFrame) -> None:
    from matplotlib.colors import LinearSegmentedColormap

    labels = {"skill_count": "Skills (total)", "programming_skill_count": "Programming", "cloud_skill_count": "Cloud",
              "libraries_skill_count": "Libraries", "databases_skill_count": "Databases",
              "analyst_tools_skill_count": "Analyst tools", "is_senior": "Senior", "work_from_home": "Remote",
              "salary_year_avg": "Salary"}
    cmap = LinearSegmentedColormap.from_list("div", DIVERGING)
    fig, ax = plt.subplots(figsize=(8.5, 7))
    im = ax.imshow(corr.values, cmap=cmap, vmin=-1, vmax=1)
    names = [labels[c] for c in corr.columns]
    ax.set_xticks(range(len(names)), names, rotation=40, ha="right")
    ax.set_yticks(range(len(names)), names)
    ax.grid(False)
    for i in range(len(names)):
        for j in range(len(names)):
            v = corr.values[i, j]
            ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=8.5,
                    color=SURFACE if abs(v) > 0.55 else INK_2)
    cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cb.outline.set_visible(False)
    cb.set_label("Spearman ρ", color=INK_2)
    ax.set_title("Feature correlations (Spearman), data_jobs 2023")
    corr.to_csv(RESULTS_DIR / "fig_feature_correlations.csv")
    save(fig, "F_feature_correlations",
         "Source: data_jobs 2023, postings with extracted skills; salary pairs use the 2.8% of postings publishing a salary.")


def run_all() -> dict:
    started = time.time()
    style()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ref, live = reference_jobs(), live_jobs()

    descriptive = A.descriptive_tables(ref, live)
    write_json("descriptive", descriptive)

    a = A.senior_skill_count_test(ref)
    write_json("A_senior_skill_count", a)
    fig_skill_count_by_seniority(ref, a)

    b_ref = A.remote_association_test(ref, "role_family", "work_from_home", "data_jobs 2023")
    b_live = A.remote_association_test(live, "job_family", "remote", "Arbeitnow snapshot 2026")
    write_json("B_remote_association", {"reference": b_ref, "live": b_live})
    fig_remote_share(ref, "role_family", "work_from_home", "Remote share by role family (2023 reference data)",
                     "B_remote_by_role_reference", "Source: data_jobs 2023. Chi-square: Cramér's V = "
                     f"{b_ref['cramers_v']:.3f} ({b_ref['effect']}).")
    fig_remote_share(live, "job_family", "remote", "Remote share by job family (live API snapshot, Oct 2026)",
                     "B_remote_by_family_live", "Source: Arbeitnow API snapshot 2026-10-08. Chi-square: Cramér's V = "
                     f"{b_live['cramers_v']:.3f} ({b_live['effect']}).")

    skills = query_df("SELECT s.name FROM market.job_skills_reference js JOIN market.skills s USING (skill_id) "
                      "GROUP BY s.name HAVING COUNT(*) >= %s", (5000,))["name"].tolist()
    c = A.senior_skill_association(ref, reference_skill_matrix(skills))
    write_json("C_senior_skill_association", c)
    fig_senior_odds_ratios(c)

    d = A.salary_model(ref)
    write_json("D_salary_model", d)
    fig_salary_coefficients(d)

    e = A.experience_skill_test(live)
    write_json("E_experience_skills_live", e)
    fig_experience_skills(live)

    corr = A.spearman_correlations(ref)
    fig_correlations(corr)

    summary = {"generated_in_seconds": round(time.time() - started, 1),
               "reference_rows": int(len(ref)), "live_rows": int(len(live)),
               "figures": sorted(p.name for p in FIG_DIR.glob("*.png"))}
    write_json("summary", summary)
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    run_all()
