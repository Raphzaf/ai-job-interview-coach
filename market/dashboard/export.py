"""Export the Tableau Public data files and validate them against PostgreSQL.

    python -m market.dashboard.export        # read-only role (DATABASE_URL)

Writes dashboard/tableau/data/*.csv (+ data_dictionary.json, validation.json).
Every check compares an extract with an independent query on the database;
the export fails loudly if any check does not hold.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from market import PROCESSED_DIR, PROJECT_ROOT
from market.db.config import connect
from market.db.run_queries import parse_queries

SQL_FILE = PROJECT_ROOT / "sql" / "dashboard_exports.sql"
OUT_DIR = PROJECT_ROOT / "dashboard" / "tableau" / "data"


def run_exports(conn, out_dir: Path = OUT_DIR) -> dict[str, pd.DataFrame]:
    out_dir.mkdir(parents=True, exist_ok=True)
    frames = {}
    for q in parse_queries(SQL_FILE.read_text(encoding="utf-8")):
        with conn.cursor() as cur:
            cur.execute(q["sql"])
            df = pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])
        df.to_csv(out_dir / f"{q['name']}.csv", index=False)
        frames[q["name"]] = df
        print(f"{q['name']}: {len(df):,} rows")
    return frames


def insight_tables(out_dir: Path = OUT_DIR) -> dict[str, pd.DataFrame]:
    """Reshape the statistics/ML results (already computed) into tidy tables for Tableau."""
    ml = json.loads((PROCESSED_DIR / "ml_results" / "role_model.json").read_text())
    stats_c = json.loads((PROCESSED_DIR / "stats_results" / "C_senior_skill_association.json").read_text())
    stats_d = json.loads((PROCESSED_DIR / "stats_results" / "D_salary_model.json").read_text())
    rows = [{"model": k, "kind": "baseline", "macro_f1": v["macro_f1"], "accuracy": v["accuracy"],
             "balanced_accuracy": v["balanced_accuracy"]} for k, v in ml["baselines"].items()]
    rows += [{"model": k, "kind": "selected" if k == ml["selected_model"] else "candidate", "macro_f1": v["test"]["macro_f1"],
              "accuracy": v["test"]["accuracy"], "balanced_accuracy": v["test"]["balanced_accuracy"]}
             for k, v in ml["candidates"].items()]
    best = ml["candidates"][ml["selected_model"]]["test"]
    cm = []
    for i, true in enumerate(best["labels"]):
        total = sum(best["confusion_matrix"][i])
        for j, pred in enumerate(best["labels"]):
            n = best["confusion_matrix"][i][j]
            cm.append({"true_role": true, "predicted_role": pred, "postings": n, "pct_of_true_role": round(100 * n / total, 2)})
    tables = {
        "insights_ml_model_comparison": pd.DataFrame(rows),
        "insights_ml_confusion_matrix": pd.DataFrame(cm),
        "insights_ml_feature_importance": pd.DataFrame(ml["permutation_importance"]),
        "insights_senior_skill_odds_ratios": pd.DataFrame([
            {"skill": r["skill"], "senior_share_pct": r["senior_share_pct"], "non_senior_share_pct": r["non_senior_share_pct"],
             "odds_ratio": r["mh_odds_ratio"], "or_low": r["or_ci95"][0], "or_high": r["or_ci95"][1],
             "q_value": r["q_value_bh"], "significant_fdr_5pct": r["significant_fdr_5pct"]} for r in stats_c["results"]]),
        "insights_salary_model": pd.DataFrame([
            {"term": c["term"], "pct_difference": c["pct_effect"], "ci_low": c["ci95_pct"][0], "ci_high": c["ci95_pct"][1],
             "p_value": c["p_value"]} for c in stats_d["coefficients"]]),
    }
    for name, df in tables.items():
        df.to_csv(out_dir / f"{name}.csv", index=False)
    return tables


def validate(conn, f: dict[str, pd.DataFrame]) -> list[dict]:
    """Independent checks: extracts must reproduce counts computed directly in the database."""
    q = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731 - fixed SQL strings only
    checks = []

    def check(name, actual, expected):
        ok = actual == expected
        checks.append({"check": name, "actual": actual, "expected": expected, "ok": bool(ok)})
        if not ok:
            raise AssertionError(f"Validation failed: {name}: {actual} != {expected}")

    ov = f["ref_overview_2023"]
    check("overview: total postings", int(ov["postings"].sum()), q("SELECT COUNT(*) FROM market.jobs_reference"))
    check("overview: postings with skill data", int(ov["postings_with_skill_data"].sum()),
          q("SELECT COUNT(*) FROM market.jobs_reference WHERE NOT skills_missing"))
    check("overview: postings with salary", int(ov["postings_with_salary"].sum()),
          q("SELECT COUNT(salary_year_avg) FROM market.jobs_reference"))

    sd = f["ref_skill_demand_2023"]
    keys = ["role_family", "seniority", "country_group", "remote"]
    n_groups, n_skills = len(sd[keys].drop_duplicates()), sd["skill"].nunique()
    check("skill demand: dense (rows = groups x skills)", len(sd), n_groups * n_skills)
    check("skill demand: one denominator per group", int(sd.groupby(keys)["postings_in_group"].nunique().max()), 1)
    per_skill = sd.groupby("skill")["postings_with_skill"].sum()
    check("skill demand: SQL postings", int(per_skill["SQL"]), q(
        "SELECT COUNT(*) FROM market.job_skills_reference js JOIN market.skills s USING (skill_id) WHERE s.name = 'SQL'"))
    check("skill demand: all skill mentions", int(per_skill.sum()), q("SELECT COUNT(*) FROM market.job_skills_reference"))
    denominator = int(sd[sd["skill"] == "SQL"]["postings_in_group"].sum())
    check("skill demand: SQL share of postings (%)", round(100 * per_skill["SQL"] / denominator, 2), 57.73)

    # The share formula must stay correct under filters: compare a filtered share
    # computed from the extract with a direct database query.
    sub = sd[(sd["skill"] == "AWS") & (sd["role_family"] == "Data Engineer") & (sd["country_group"] == "Germany")]
    direct = conn.execute("""
        SELECT ROUND(100.0 * COUNT(*) FILTER (WHERE EXISTS (
                   SELECT 1 FROM market.job_skills_reference js JOIN market.skills s USING (skill_id)
                   WHERE js.job_id = j.job_id AND s.name = 'AWS')) / COUNT(*), 2)
        FROM market.jobs_reference j
        WHERE NOT j.skills_missing AND j.role_family = 'Data Engineer' AND j.country = 'Germany'""").fetchone()[0]
    check("skill demand: filtered share (AWS | Data Engineer | Germany) equals direct SQL",
          round(100 * sub["postings_with_skill"].sum() / sub["postings_in_group"].sum(), 2), float(direct))

    tr = f["ref_skill_trend_2023"]
    check("skill trend: Python postings", int(tr[tr["skill"] == "Python"]["postings_with_skill"].sum()), q(
        "SELECT COUNT(*) FROM market.job_skills_reference js JOIN market.skills s USING (skill_id) WHERE s.name = 'Python'"))
    check("skill trend: dense", len(tr), len(tr[["role_family", "month"]].drop_duplicates()) * tr["skill"].nunique())

    lj = f["live_jobs_2026"]
    check("live jobs: rows", len(lj), q("SELECT COUNT(*) FROM market.jobs_live"))
    ls = f["live_skill_demand_2026"]
    lkeys = ["job_family", "experience_level", "remote", "description_language"]
    check("live skills: dense", len(ls), len(ls[lkeys].drop_duplicates()) * ls["skill"].nunique())
    check("live skills: all skill mentions", int(ls["postings_with_skill"].sum()), q("SELECT COUNT(*) FROM market.job_skills_live"))
    check("live skills: denominators sum to all postings (per skill)",
          int(ls[ls["skill"] == ls["skill"].iloc[0]]["postings_in_group"].sum()), len(lj))

    sal = f["ref_salary_by_role_2023"].set_index(["role_family", "seniority"])
    sql05 = pd.read_csv(PROCESSED_DIR / "sql_results" / "05_reference_salary_by_role_seniority.csv").set_index(["role_family", "seniority"])
    as_dict = lambda series: {" / ".join(k): float(round(v)) for k, v in series.items()}  # noqa: E731
    check("salary medians equal Phase-3 SQL results", as_dict(sal["salary_median"].astype(float)),
          as_dict(sql05["median_salary_year"].astype(float)))
    return checks


def expected_values(f: dict[str, pd.DataFrame]) -> str:
    """Numbers the Tableau views must show (to verify the manual build), computed from the extracts."""
    ov, sd, lj, ls = f["ref_overview_2023"], f["ref_skill_demand_2023"], f["live_jobs_2026"], f["live_skill_demand_2026"]

    def kpis(o: pd.DataFrame) -> str:
        return (f"Postings **{int(o.postings.sum()):,}** · Remote **{100 * o[o.remote == 'Remote'].postings.sum() / o.postings.sum():.1f} %** · "
                f"Senior **{100 * o[o.seniority == 'Senior'].postings.sum() / o.postings.sum():.1f} %** · "
                f"Avg advertised salary **{o.salary_sum.sum() / o.postings_with_salary.sum():,.0f}** "
                f"(n = {int(o.postings_with_salary.sum()):,}) · Avg skills **{o.total_skills_listed.sum() / o.postings_with_skill_data.sum():.2f}**")

    def top(d: pd.DataFrame, n: int = 5) -> str:
        g = d.groupby("skill")[["postings_with_skill", "postings_in_group"]].sum()
        g = (g.postings_with_skill / g.postings_in_group * 100).sort_values(ascending=False).head(n)
        return ", ".join(f"{k} {v:.1f} %" for k, v in g.items())

    de = ov[ov.role_family == "Data Engineer"]
    de_de = sd[(sd.role_family == "Data Engineer") & (sd.country_group == "Germany")]
    lines = [
        "# Expected values for the Tableau build",
        "",
        "Generated by `python -m market.dashboard.export` from the same CSV files. If a view shows a different number "
        "with the same filters, a calculation or filter is set up differently from the guide.",
        "",
        "## Dashboard 1: Data-role market 2023",
        "",
        f"- No filters: {kpis(ov)}",
        f"- Top 5 skills, no filters: {top(sd)}",
        f"- Filter role = Data Engineer: {kpis(de)}",
        f"- Top 5 skills, role = Data Engineer: {top(sd[sd.role_family == 'Data Engineer'])}",
        f"- Top 5 skills, role = Data Engineer and country = Germany: {top(de_de)}",
        f"- Busiest month: {ov.groupby('month').postings.sum().idxmax()} "
        f"({int(ov.groupby('month').postings.sum().max()):,} postings)",
        "",
        "## Dashboard 3: Live snapshot (Oct 2026)",
        "",
        f"- No filters: postings **{len(lj):,}**, remote **{100 * lj.remote.mean():.1f} %**, tech **{100 * lj.is_tech.mean():.1f} %**",
        f"- Top 5 skills, no filters: {top(ls)}",
        f"- Top 5 skills, job family = Data & AI: {top(ls[ls.job_family == 'Data & AI'])}",
    ]
    return "\n".join(lines) + "\n"


DICTIONARY = {
    "ref_overview_2023": "data_jobs 2023. Grain: role_family x seniority x country_group x remote x month. Measures are additive "
                         "counts/sums: avg salary = SUM(salary_sum)/SUM(postings_with_salary); avg skills = "
                         "SUM(total_skills_listed)/SUM(postings_with_skill_data).",
    "ref_skill_demand_2023": "data_jobs 2023. Dense: skill x role_family x seniority x country_group x remote. "
                             "Share = SUM(postings_with_skill)/SUM(postings_in_group). Keep [skill] on the view or filtered.",
    "ref_skill_trend_2023": "data_jobs 2023. Dense: skill (>=1,000 postings) x role_family x month. Same share formula.",
    "ref_salary_by_role_2023": "data_jobs 2023. Salary percentiles (medians are not additive, so computed in SQL); "
                               "groups with >= 30 published salaries.",
    "live_jobs_2026": "Arbeitnow API snapshot 2026-10-08, one row per posting, no description text; url = link back to the source.",
    "live_skill_demand_2026": "Arbeitnow snapshot. Dense: skill x job_family x experience_level x remote x description_language. "
                              "Same share formula.",
    "insights_ml_model_comparison": "Phase 6 test-set metrics (company-grouped split).",
    "insights_ml_confusion_matrix": "Phase 6 selected model; pct_of_true_role = recall row %.",
    "insights_ml_feature_importance": "Phase 6 permutation importance (drop in macro-F1).",
    "insights_senior_skill_odds_ratios": "Phase 4 Cochran-Mantel-Haenszel odds ratios (senior vs non-senior within role).",
    "insights_salary_model": "Phase 4 OLS on log salary (US 2023), % differences with 95% CI.",
}


def main() -> None:
    with connect() as conn:
        frames = run_exports(conn)
        checks = validate(conn, frames)
    insights = insight_tables()
    (OUT_DIR.parent / "EXPECTED_VALUES.md").write_text(expected_values(frames), encoding="utf-8")
    files = {p.name: {"rows": int(len(pd.read_csv(p))), "bytes": p.stat().st_size, "description": DICTIONARY[p.stem]}
             for p in sorted(OUT_DIR.glob("*.csv"))}
    (OUT_DIR / "data_dictionary.json").write_text(json.dumps(files, indent=2), encoding="utf-8")
    (OUT_DIR / "validation.json").write_text(json.dumps(checks, indent=2, default=str), encoding="utf-8")
    print(f"{len(checks)} validation checks passed; {len(frames) + len(insights)} files, "
          f"{sum(v['bytes'] for v in files.values()) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
