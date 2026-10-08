"""Reproducible Phase-2 pipeline: raw sources -> cleaned tables + profiling reports.

    python -m market.pipeline                      # both sources (downloads the reference CSV if needed)
    python -m market.pipeline --skip-data-jobs     # Arbeitnow only (fast)

Outputs
- data/processed/arbeitnow/            jobs.csv, job_skills.csv  (committed: no free text)
                                       descriptions.csv.gz       (git-ignored: may contain contact details)
- data/processed/data_jobs/            jobs.csv.gz, job_skills.csv.gz (git-ignored, regenerated from the pinned CSV)
- data/processed/skills.csv            shared skill vocabulary with demand counts per source (committed)
- data/processed/reports/*.json        profiles + cleaning steps (committed)
"""

from __future__ import annotations

import argparse
import json
import time

import pandas as pd

from app.matching.skills import SKILL_TAXONOMY, skill_category
from market import PROCESSED_DIR, RAW_DIR
from market.cleaning_arbeitnow import clean_arbeitnow
from market.cleaning_data_jobs import clean_data_jobs
from market.ingestion import hf_data_jobs
from market.ingestion.arbeitnow import latest_snapshot, load_snapshot
from market.profiling import profile, top_counts

REPORTS = PROCESSED_DIR / "reports"


def skill_demand(jobs: pd.DataFrame, job_skills: pd.DataFrame, n: int = 30) -> dict:
    """Top skills as a share of POSTINGS (not of skill mentions).

    `jobs` must be the denominator population: for data_jobs, only postings
    whose skills were extracted (a missing list is unknown, not "no skills").
    """
    counts = job_skills[job_skills["job_id"].isin(jobs["job_id"])].groupby("skill")["job_id"].nunique()
    counts = counts.sort_values(ascending=False).head(n)
    return {"denominator_postings": int(len(jobs)),
            "skills": [{"skill": k, "postings": int(v), "share_pct": round(v / len(jobs) * 100, 2)} for k, v in counts.items()]}


def write_json(path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def run_arbeitnow(snapshot=None) -> tuple[pd.DataFrame, pd.DataFrame]:
    folder = snapshot or latest_snapshot()
    raw = load_snapshot(folder)
    raw_df = pd.DataFrame(raw)
    jobs, job_skills, descriptions, report = clean_arbeitnow(raw, folder.name)
    out = PROCESSED_DIR / "arbeitnow"
    out.mkdir(parents=True, exist_ok=True)
    jobs.to_csv(out / "jobs.csv", index=False)
    job_skills.to_csv(out / "job_skills.csv", index=False)
    descriptions.to_csv(out / "descriptions.csv.gz", index=False)
    manifest = json.loads((folder / "manifest.json").read_text())
    write_json(REPORTS / "arbeitnow.json", {
        "snapshot": folder.name,
        "manifest": {k: v for k, v in manifest.items() if k != "pages"},
        "raw_profile": profile(raw_df, "arbeitnow_raw", list_columns=("tags", "job_types")),
        "cleaning_steps": report.steps,
        "processed_profile": profile(jobs, "arbeitnow_jobs"),
        "distributions": {c: top_counts(jobs[c]) for c in [
            "job_family", "experience_level", "seniority_from_title", "schedule", "contract_type",
            "description_language", "remote", "city"]},
        "top_skills": skill_demand(jobs, job_skills),
        "jobs_with_at_least_one_skill": int((jobs["skill_count"] > 0).sum()),
    })
    print(f"Arbeitnow: {len(raw_df)} raw -> {len(jobs)} jobs, {len(job_skills)} job-skill rows")
    return jobs, job_skills


def run_data_jobs() -> tuple[pd.DataFrame, pd.DataFrame]:
    csv = hf_data_jobs.download()
    raw_df = pd.read_csv(csv)
    jobs, job_skills, report = clean_data_jobs(csv)
    out = PROCESSED_DIR / "data_jobs"
    out.mkdir(parents=True, exist_ok=True)
    jobs.to_csv(out / "jobs.csv.gz", index=False)
    job_skills.to_csv(out / "job_skills.csv.gz", index=False)
    write_json(REPORTS / "data_jobs.json", {
        "source": json.loads((RAW_DIR / "hf_data_jobs" / "manifest.json").read_text()),
        "raw_profile": profile(raw_df, "data_jobs_raw"),
        "cleaning_steps": report.steps,
        "processed_profile": profile(jobs, "data_jobs_jobs"),
        "distributions": {c: top_counts(jobs[c]) for c in [
            "job_title_short", "role_family", "is_senior", "title_seniority", "schedule", "job_work_from_home",
            "country", "posted_month"]},
        "country_repair": {
            "rows_repaired": int(jobs["country_repaired"].sum()),
            "to_united_states": int((jobs["country_repaired"] & (jobs["country"] == "United States")).sum()),
            "to_unknown": int((jobs["country_repaired"] & jobs["country"].isna()).sum()),
        },
        "salary_rows": int(jobs["has_salary"].sum()),
        "top_skills": skill_demand(jobs[~jobs["skills_missing"]], job_skills),
        "skill_mentions_in_coach_taxonomy_pct": round(float(job_skills["in_coach_taxonomy"].mean() * 100), 2),
        "distinct_skills": int(job_skills["skill"].nunique()),
    })
    print(f"data_jobs: {len(raw_df)} raw -> {len(jobs)} jobs, {len(job_skills)} job-skill rows")
    return jobs[~jobs["skills_missing"]], job_skills  # denominator for skill shares


def build_skill_vocabulary(sources: dict[str, tuple[pd.DataFrame, pd.DataFrame]]) -> pd.DataFrame:
    """One row per skill with its category and its demand in each source (share of postings).

    Shares are computed within each source only (denominator = that source's
    postings with skill information); they are side-by-side columns, not a
    merged population, and must not be read as a change over time.
    """
    frames = []
    for name, (jobs, job_skills) in sources.items():
        counts = job_skills.groupby("skill")["job_id"].nunique().rename(f"{name}_postings")
        share = (counts / len(jobs) * 100).round(3).rename(f"{name}_share_pct")
        frames += [counts, share]
    vocab = pd.concat(frames, axis=1).fillna(0).reset_index().rename(columns={"index": "skill"})
    vocab["in_coach_taxonomy"] = vocab["skill"].isin(SKILL_TAXONOMY)
    vocab["category"] = vocab["skill"].map(lambda s: skill_category(s) if s in SKILL_TAXONOMY else "Other")
    return vocab.sort_values(vocab.columns[1], ascending=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--skip-data-jobs", action="store_true")
    args = parser.parse_args()
    started = time.time()
    sources = {"arbeitnow": run_arbeitnow()}
    processed_ref = PROCESSED_DIR / "data_jobs"
    if not args.skip_data_jobs:
        sources["data_jobs"] = run_data_jobs()
    elif (processed_ref / "job_skills.csv.gz").exists():
        # Reuse the already-processed reference tables so the shared skill
        # vocabulary always covers both sources.
        ref_jobs = pd.read_csv(processed_ref / "jobs.csv.gz", usecols=["job_id", "skills_missing"])
        sources["data_jobs"] = (ref_jobs[~ref_jobs["skills_missing"]],
                                pd.read_csv(processed_ref / "job_skills.csv.gz", usecols=["job_id", "skill"]))
    vocab = build_skill_vocabulary(sources)
    vocab.to_csv(PROCESSED_DIR / "skills.csv", index=False)
    print(f"Skill vocabulary: {len(vocab)} skills. Done in {time.time() - started:.0f}s")


if __name__ == "__main__":
    main()
